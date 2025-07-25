# autoclaim.py
from dotenv import load_dotenv
load_dotenv()

import os
import time
import json
import re
import requests
from datetime import datetime, timezone
import eospy.cleos as cleos_module
import eospy.keys as keys_module
from antelopy.abi_cache import AbiCache

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich.align import Align
from rich import box

CLAIM_INTERVAL = 3600  # en secondes
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

def format_uptime(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"

def fetch_and_get_issue(txid):
    resp = requests.get(
        "https://test.ultra.eosusa.io/v2/history/get_transaction",
        params={"id": txid}
    )
    if not resp.ok:
        console.log(f"[red]HTTP error:[/] {resp.status_code}")
        return 0.0, None

    for act in resp.json().get("actions", []):
        if act["act"]["account"] == "eosio.token" and act["act"]["name"] == "issue":
            qty = act["act"]["data"]["quantity"]
            num, unit = qty.split()
            amt = float(num)
            memo = act["act"]["data"]["memo"]
            console.log(
                Panel(
                    f"[green]Received:[/] {amt:.2f} {unit}\n[yellow]Memo:[/] {memo}",
                    title=f"TX {txid}", border_style="blue"
                )
            )
            return amt, unit
    return 0.0, None

def print_totals_table(totals: dict[str, float]):
    table = Table(
        title="📊 Total Collected",
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

    # Précharge toutes les ABIs
    for m in MINES:
        abi.read_abi(m["contract"])

    start = time.time()
    totals: dict[str, float] = {}

    while True:
        console.clear()

        # Header : une ligne par mine, ID en bright_cyan
        uptime = format_uptime(time.time() - start)
        header_lines = [
            f"• {m['contract']}::{m['action']} (id=[bright_cyan]{m['uniq_id']}[/bright_cyan])"
            for m in MINES
        ]
        header = Panel(
            f"[bold cyan]🚀 Auto‑claim running[/]\n"
            f"[yellow]Uptime:[/] {uptime}   [green]Interval:[/] {CLAIM_INTERVAL}s\n\n"
            f"[bold]Mines to claim:[/]\n"
            + "\n".join(header_lines)
            + "\n\n(Ctrl+C to stop)",
            border_style="cyan"
        )
        console.print(header)

        console.print("\n[bold blue]→ Starting new claim cycle[/]")
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

            # retry loop pour rate‑limit
            while True:
                try:
                    resp = abi.sign_and_push(cleos, [key], trx)
                    # Correction ici :
                    if isinstance(resp, dict) and "transaction_id" in resp:
                        txid = resp["transaction_id"]
                    else:
                        console.print(f"[bold red]Unexpected response from sign_and_push:[/] {resp}")
                        break
                    amt, unit = fetch_and_get_issue(txid)
                    if unit:
                        totals[unit] = totals.get(unit, 0.0) + amt
                    break
                except Exception as e:
                    err = str(e)
                    mm = re.search(r"execution_rate_limit_till_time:\s*([0-9\-T:\.]+)", err)
                    if mm:
                        tstr = mm.group(1)
                        limit_dt = datetime.fromisoformat(tstr).replace(tzinfo=timezone.utc)
                        wait = (limit_dt - datetime.now(timezone.utc)).total_seconds()
                        if wait > 0:
                            time.sleep(wait)
                            continue
                    console.print(f"[bold red]Error on claim {m['uniq_id']}:[/] {e}")
                    break

        print_totals_table(totals)

        with Progress(
            "[cyan]Waiting for next cycle…[/]",
            BarColumn(bar_width=None),
            TimeRemainingColumn(),
            console=console,
            transient=False
        ) as progress:
            task = progress.add_task("", total=CLAIM_INTERVAL)
            while not progress.finished:
                progress.update(task, advance=1)
                time.sleep(1)

if __name__ == "__main__":
    main()
