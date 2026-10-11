"""Auto-exit robot for the LOCAL Anvil fork: python -m defi_risk.autoexit --loop 2

Watches the same signals as forkwatch and sells the fund's PT into the pool, for real (a transaction from the
fund through the DemoSeller), when a pocket's exit window is about to close:
  - PT-sUSDe, PT-sUSDS: USDe/USDS still off its peg AND the oracle challenge has less than --margin hours left
    (default 2). A short dip that recovers before the switch never triggers a sale.
  - PT-reUSD: as soon as the share price falls (the oracle follows the pool within 15 min: no time to wait).
  - If the oracle already switched, it still tries: last chance before liquidators fill the pool.
--now sells at the first signal instead. --only PT-sUSDe limits it to one pocket.
Each sale is written to dashboard/autoexit.json; forkwatch then shows the pocket as "exited".
"""
import json
import sys
import time

from . import forkwatch as fw

LOG = fw.ROOT / "dashboard" / "autoexit.json"


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


_should_sell = fw.exit_rule  # the rule lives in forkwatch, which also shows what it would have saved


def _sell(t, pt_amount):
    unit = 10 ** t["pt_decimals"]
    data = "0x" + fw.SEL["sell"] + t["pool"][2:].lower().rjust(64, "0") + hex(int(pt_amount * unit))[2:].rjust(64, "0")
    r = fw._rpc("eth_sendTransaction", [{"from": fw.FUND, "to": fw.SELLER, "data": data, "gas": hex(3_000_000)}])
    if "result" not in r:
        raise RuntimeError(r.get("error"))
    tx = r["result"]
    rec = {}
    for _ in range(30):  # Anvil mines at once, but the receipt can take a moment to show up
        rec = fw._rpc("eth_getTransactionReceipt", [tx]).get("result") or {}
        if rec:
            break
        time.sleep(0.5)
    return tx, rec.get("status") == "0x1", int(rec.get("blockNumber", "0x0"), 16)


def step(margin, now_mode, only):
    blk = fw._rpc("eth_getBlockByNumber", ["latest", False])["result"]
    now = int(blk["timestamp"], 16)
    refs = fw._references()
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    for t in fw.TOKENS:
        if only and t["name"] != only:
            continue
        tok = fw._token(t, now)
        book = fw._book(t, tok, refs.get(t["name"]))
        if book.get("status") in ("not set up", "exited", None) or not book.get("sellable_pt"):
            continue  # nothing held (already sold, or step 0 not done) or nothing sellable any more
        why = _should_sell(tok, book, margin, now_mode)
        if not why:
            continue
        pt = book["sellable_pt"]
        tx, ok, block = _sell(t, pt)
        line = f"{t['name']}: {why} -> sold {pt:,.0f} PT for about ${book['sell_now_usd']:,.0f}" if ok else \
            f"{t['name']}: {why} -> sale REVERTED (pool refused)"
        print(time.strftime("%H:%M:%S"), line, f"(tx {tx[:12]}…, block {block})", flush=True)
        if ok:
            o = tok.get("oracle") or {}
            log[t["name"]] = {"sold_pt": pt, "proceeds_usd": book["sell_now_usd"], "block": block, "tx": tx,
                              "reason": why, "hours_before_switch": o.get("challenge_hours_left")}
            LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


def main():
    loop = float(_arg("--loop", 2))
    margin = float(_arg("--margin", 2))
    only = _arg("--only", None)
    fw.SELLER = _arg("--seller", fw.SELLER)
    now_mode = "--now" in sys.argv
    LOG.write_text("{}", encoding="utf-8")  # fresh log: a reset fork gives the fund its PT back
    print(f"auto-exit armed: {'first signal' if now_mode else f'sell when < {margin:g} h before the oracle switches'}"
          f"{', ' + only + ' only' if only else ''}. Ctrl+C to stop.", flush=True)
    while True:
        try:
            step(margin, now_mode, only)
        except Exception as e:
            print(f"local chain not reachable or read failed ({str(e)[:80]}), retrying...", flush=True)
        time.sleep(loop)


if __name__ == "__main__":
    main()
