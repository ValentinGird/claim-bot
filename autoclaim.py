# autoclaim.py
from dotenv import load_dotenv
load_dotenv()

import os
import json
import re
import requests
from datetime import datetime, timezone
import eospy.cleos as cleos_module
import eospy.keys as keys_module
from antelopy.abi_cache import AbiCache

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich import box

console = Console()

# Charge la liste de mines depuis mines.json
try:
    with open("mines.json", "r", encoding="utf-8") as f:
        MINES = json.load(f)
except FileNotFoundError:
    console.print("[bold red]mines.json not found![/]")
    exit(1)
except json.JSONDecodeError as e:
    console.print(f"[bold red]Error parsing mines.json:[/] {e}")
    exit(1)

if not MINES:
    console.print("[bold yellow]Warning:[/] mines.json is empty, nothing to claim.")
    exit(0)

def fetch_and_get_issue(txid):
    resp = requests.get(
        "https://test.ultra.eosusa.io/v2/history/get_transaction",
        params={"id": txid}
    )
    if not resp.ok:
        console.log(f"[red]HTTP error:[/] {resp.status_code}")
        return 0.0, None

    try:
        actions = resp.json().get("actions", [])
    except Exception as e:
        console.print(f"[red]JSON decode error on fetch_and_get_issue:[/] {e}")
        return 0.0, None

    for act in actions:
        if act.get("act", {}).get("account") == "eosio.token" and act.get("act", {}).get("name") == "issue":
            qty = act["act"]["data"]["quantity"]
            if isinstance(qty, dict):
                qty = qty.get("quantity", "")
            num, unit = str(qty).split()
            amt = float(num)
            memo = act["act"]["data"]["memo"]
            console.print(
                Panel(
                    f"[green]Received:[/] {amt:.2f} {unit}\n[yellow]Memo:[/] {memo}",
                    title=f"TX {txid}", border_style="blue"
                )
            )
            return amt, unit
    return 0.0, None

def print_totals_table(totals: dict[str, float]):
    table = Table(
        title="📊 Total Collected This Run",
        title_justify="center",
        box=box.SIMPLE_HEAVY,
        expand=False
    )
    table.add_column("Resource", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="magenta")
    for unit, amt in totals.items():
        table.add_row(unit, f"{amt:.2f}")
    console.print(Align(table, align="center"))

def main():
    pk = os.getenv("ULTRA_PRIVATE_KEY")
    if not pk:
        console.print("[bold red]No private key found![/]")
        return

    account = os.getenv("ULTRA_ACCOUNT")
    endpoint = "https://testnet.ultra.eosrio.io"
    cleos = cleos_module.Cleos(url=endpoint)
    key   = keys_module.EOSKey(pk)
    abi   = AbiCache(chain_endpoint=endpoint, chain_package="eospy")

    for m in MINES:
        abi.read_abi(m["contract"])

    totals: dict[str, float] = {}

    console.print("\n[bold blue]→ Starting claim cycle[/]")
    for m in MINES:
        console.print(
            f"[dim]Claiming[/] [white]{m['contract']}::{m['action']}[/white] "
            f"(id=[bright_cyan]{m['uniq_id']}[/bright_cyan])"
        )
        trx = {
            "actions": [{
                "account":      m["contract"],
                "name":         m["action"],
                "authorization":[{"actor": account, "permission": "aom.claim"}],
                "data": {
                    "uniq_id":    m["uniq_id"],
                    "uniq_owner": account
                }
            }]
        }

        try:
            resp = abi.sign_and_push(cleos, [key], trx)
            if isinstance(resp, dict) and "transaction_id" in resp:
                txid = resp["transaction_id"]
            else:
                console.print(f"[bold red]Unexpected response from sign_and_push:[/] {resp}")
                continue
            amt, unit = fetch_and_get_issue(txid)
            if unit:
                totals[unit] = totals.get(unit, 0.0) + amt
        except Exception as e:
            console.print(f"[bold red]Error on claim {m['uniq_id']}:[/] {e}")
            continue

    print_totals_table(totals)

if __name__ == "__main__":
    main()
