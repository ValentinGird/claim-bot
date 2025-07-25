from dotenv import load_dotenv 
load_dotenv()

import os
import json
import requests
import time
from datetime import datetime, timezone
import eospy.cleos as cleos_module
import eospy.keys as keys_module
from antelopy import AbiCache

# Charge la liste de mines depuis mines.json
try:
    with open("mines.json", "r", encoding="utf-8") as f:
        MINES = json.load(f)
except FileNotFoundError:
    print("❌ mines.json not found!", flush=True)
    exit(1)
except json.JSONDecodeError as e:
    print(f"❌ Error parsing mines.json: {e}", flush=True)
    exit(1)

if not MINES:
    print("⚠️  mines.json is empty, nothing to claim.", flush=True)
    exit(0)

def fetch_and_get_issue(txid):
    try:
        resp = requests.get(
            "https://test.ultra.eosusa.io/v2/history/get_transaction",
            params={"id": txid},
        )
        resp.raise_for_status()
        actions = resp.json().get("actions", [])

        for act in actions:
            if (
                act.get("act", {}).get("account") == "eosio.token"
                and act.get("act", {}).get("name") == "issue"
            ):
                data = act["act"]["data"]
                qty = data.get("quantity")
                if isinstance(qty, dict):
                    qty = qty.get("quantity", "")
                qty = str(qty)
                if " " not in qty:
                    return 0.0, None
                num, unit = qty.split()
                amt = float(num)
                memo = data.get("memo", "")
                print(f"[✅] +{amt:.8f} {unit} | {memo}", flush=True)
                return amt, unit

        print(f"[ℹ️] TX {txid} analysée, aucune issue détectée", flush=True)
    except Exception as e:
        print(f"[ERROR] fetch_and_get_issue: {e}", flush=True)
    return 0.0, None

def print_totals_table(totals):
    print("\n=== Total Collected This Run ===", flush=True)
    print("===============================", flush=True)
    if not totals:
        print("Aucune ressource collectée.", flush=True)
    else:
        for unit, amt in totals.items():
            print(f"{unit}: {amt:.2f}", flush=True)
    print("===============================\n", flush=True)

def claim_cycle():
    print(
        f"\n=== Starting claim cycle at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC ===\n",
        flush=True
    )

    pk = os.getenv("ULTRA_PRIVATE_KEY")
    if not pk:
        print("❌ No private key found!", flush=True)
        return

    account = os.getenv("ULTRA_ACCOUNT")
    endpoint = "https://testnet.ultra.eosrio.io"
    cleos = cleos_module.Cleos(url=endpoint)
    key = keys_module.EOSKey(pk)
    abi = AbiCache(chain_endpoint=endpoint, chain_package="eospy")

    for m in MINES:
        abi.read_abi(m["contract"])

    totals = {}

    for m in MINES:
        print(f"🔄 Claiming {m['contract']}::{m['action']} (ID {m['uniq_id']})...", flush=True)
        trx = {
            "actions": [
                {
                    "account": m["contract"],
                    "name": m["action"],
                    "authorization": [{"actor": account, "permission": "aom.claim"}],
                    "data": {
                        "uniq_id": int(m["uniq_id"]),
                        "uniq_owner": account
                    },
                }
            ]
        }

        try:
            resp = abi.sign_and_push(cleos, [key], trx)
            if isinstance(resp, dict) and "transaction_id" in resp:
                txid = resp["transaction_id"]
                amt, unit = fetch_and_get_issue(txid)
                if unit:
                    totals[unit] = totals.get(unit, 0.0) + amt
                    print(f"[✔️] Collected: +{amt:.4f} {unit} (Total: {totals[unit]:.4f})", flush=True)
            else:
                print(f"[ERROR] Unexpected response: {resp}", flush=True)
        except Exception as e:
            print(f"[ERROR] on claim ID {m['uniq_id']}: {e}", flush=True)

        # Pause de 30 secondes entre chaque mine
        time.sleep(30)

    print_totals_table(totals)

if __name__ == "__main__":
    while True:
        claim_cycle()
        print("[⏳] Sleeping 3600 seconds until next cycle...\n", flush=True)
        time.sleep(3600)
