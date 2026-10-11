"""Map one Pendle PT live, layer by layer: python -m defi_risk.map USD3 2026-12-17

Same discovery as the dashboard (Pendle, Morpho, DefiLlama, on-chain reads), printed along the
brief's five layers, then what this PT shares with the three positions already in the book.
"""
import json
import sys
import time
from pathlib import Path

from .discover import discover

BOOK = Path(__file__).resolve().parents[2] / "dashboard" / "data.json"
LAYERS = [
    ("Layer 4 · PT market (where you exit)", {"amm", "offchain"}),
    ("Layer 2 · Yield source & issuer", {"asset", "issuer", "perp_venue", "oes", "infra"}),
    ("Layer 5 · Lending markets (hold the PT, can force-sell it)", {"lending", "vault", "stablecoin"}),
    ("Layer 3 · Oracles (decide when liquidations start)", {"oracle", "price_feed"}),
    ("Layer 1 · Settlement", {"chain", "protocol"}),
]


def _money(x):
    return f"${x / 1e6:,.1f}M" if x and x >= 1e6 else f"${x:,.0f}" if x else "-"


def _describe(n):
    d = n.data
    if n.kind == "amm":
        return f"liquidity {_money(d.get('liquidity_usd'))}, implied APY {d.get('implied_apy', 0):.2%}"
    if n.kind == "issuer":
        tvl = sum((d.get("tvl_by_chain") or {}).values())
        return f"TVL {_money(tvl)}" if tvl else "not on DefiLlama"
    if n.kind == "lending":
        return (f"collateral {_money(d.get('collateral_usd'))}, borrowed {_money(d.get('borrow_usd'))}, "
                f"utilisation {d.get('utilization', 0):.0%}")
    if n.kind == "vault":
        legs = [f"{a['share_of_market_supply']:.0%} of {a['market']}" for a in d.get("allocations", {}).values()]
        return "lends " + "; ".join(legs) if legs else ""
    if n.kind == "oracle":
        sens = d.get("primary_market_sensitive", d.get("market_sensitive"))
        reads = [r for r in (d.get("primary_reads") or d.get("reads") or []) if not r.lower().startswith("dummy")]
        labelled = [r for r in reads if r != "unlabelled feed"]
        if sens is False:
            how = "ignores the PT market (linear discount)"
        elif sens and labelled:
            how = "reads a market feed"
        elif sens:
            how = "reads an unlabelled feed: whether it follows the market is not confirmed"
        else:
            how = "unknown design"
        extra = f", backup after {d['timelock_hours']:.0f} h challenge" if d.get("timelock_hours") else ""
        return f"{how}{extra}; reads: {', '.join(reads) or '-'}"
    return ""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python -m defi_risk.map <name> [expiry YYYY-MM-DD]")
    name, expiry = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    t = time.time()
    g = discover(name, expiry)
    pos = next(n for n in g.nodes.values() if n.kind == "position")
    print(f"\n{pos.label}: {len(g.nodes)} dependencies and {len(g.edges)} links found in {time.time() - t:.1f} s\n")
    for title, kinds in LAYERS:
        nodes = [n for n in g.nodes.values() if n.kind in kinds]
        nodes = [n for n in nodes if not (n.kind == "price_feed" and n.label.lower().startswith("dummy"))]
        if not nodes:
            continue
        print(title)
        for n in nodes:
            info = _describe(n)
            print(f"   - {n.label}" + (f"  ({info})" if info else ""))
    try:
        book = json.loads(BOOK.read_text())
        ids = {n["id"]: n["label"] for n in book["graph"]["nodes"]}
        shared = [g.nodes[i].label for i in g.nodes if i in ids and g.nodes[i].kind not in ("position",)]
        print(f"\nShared with the book (PT-sUSDe, PT-reUSD, PT-sUSDS): {', '.join(shared) or 'nothing'}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
