"""Ecosystem scan: map every Pendle PT used as Morpho collateral and rank the dependencies they share.

Usage: python -m defi_risk.ecosystem [min_collateral_usd]   (default $1M)

For each shared node it reports how many positions depend on it and how much Morpho collateral
sits behind those positions: the places where one failure would hit many PTs at once.
"""
import json
import sys
from pathlib import Path

from . import sources
from .discover import contagion_paths, discover, reach
from .graph import Graph

OUT = Path(__file__).resolve().parents[2] / "dashboard" / "ecosystem.json"
SKIP_KINDS = {"chain", "protocol", "offchain"}  # shared by construction, not informative


def candidates(min_collateral):
    """(name, expiry, collateral) of active Pendle PTs with at least `min_collateral` on Morpho."""
    out = []
    for m in sources.pendle_active_markets(1):
        pt = m["pt"].split("-", 1)[1]
        try:
            coll = sum((x["state"]["collateralAssetsUsd"] or 0) for x in sources.morpho_markets_by_collateral(pt))
        except Exception:
            continue
        if coll >= min_collateral:
            out.append((m["name"], m["expiry"][:10], coll))
    return sorted(out, key=lambda x: -x[2])


def scan(min_collateral=1e6):
    g = Graph()
    mapped, failed = [], []
    for name, expiry, coll in candidates(min_collateral):
        try:
            discover(name, expiry, g=g)
            mapped.append({"position": f"PT-{name} ({expiry})", "morpho_collateral_usd": coll})
        except Exception as e:  # one odd market must not stop the scan
            failed.append({"position": f"PT-{name} ({expiry})", "error": str(e)[:120]})
    positions = [n for n in g.nodes.values() if n.kind == "position"]
    coll_of = {}
    for e in g.edges:
        if e.relation == "holds_as_collateral":
            coll_of[e.target] = coll_of.get(e.target, 0) + (e.exposure_usd or 0)
    exposure = {}
    for p in positions:
        for n in reach(g, p.id):
            if g.nodes[n].kind in SKIP_KINDS:
                continue
            exposure.setdefault(n, set()).add(p.id)
    shared = sorted(
        ({"node": g.nodes[n].label, "kind": g.nodes[n].kind, "positions": len(ps),
          "collateral_behind_usd": sum(coll_of.get(p, 0) for p in ps),
          "names": sorted(g.nodes[p].label.split(" ")[0] for p in ps)}
         for n, ps in exposure.items() if len(ps) > 1),
        key=lambda x: (-x["positions"], -x["collateral_behind_usd"]))
    oracles, blind = {}, {"follows_market": 0, "ignores_market": 0, "unknown": 0}
    for n in g.nodes.values():
        if n.kind != "oracle":
            continue
        oracles[n.data.get("pattern", "unknown")] = oracles.get(n.data.get("pattern", "unknown"), 0) + 1
        # what Morpho uses today: the primary leg for primary/backup oracles
        sens = n.data.get("primary_market_sensitive", n.data.get("market_sensitive"))
        blind["unknown" if sens is None else "follows_market" if sens else "ignores_market"] += 1
    return {"mapped": mapped, "failed": failed, "nodes": len(g.nodes), "edges": len(g.edges),
            "shared": shared, "oracle_patterns": oracles, "oracle_market_sensitivity": blind, "contagion_paths": contagion_paths(g)}


def main():
    min_coll = float(sys.argv[1]) if len(sys.argv) > 1 else 1e6
    r = scan(min_coll)
    OUT.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    print(f"{len(r['mapped'])} positions mapped ({len(r['failed'])} failed), {r['nodes']} nodes, {r['edges']} edges")
    print("oracle patterns:", r["oracle_patterns"])
    print("lending oracles vs the PT market price:", r["oracle_market_sensitivity"])
    print(f"\n{'shared dependency':45} {'kind':11} {'PTs':>4} {'Morpho collateral behind':>25}")
    for s in r["shared"][:15]:
        print(f"{s['node'][:45]:45} {s['kind']:11} {s['positions']:>4} {s['collateral_behind_usd'] / 1e6:>22,.1f}M")
    print(f"\n{len(r['contagion_paths'])} vaults lend to two or more mapped PTs")
    for c in r["contagion_paths"][:8]:
        print(f"  {c['vault']}: " + ", ".join(f"{l['position'].split(' ')[0]} {l['share_of_market_supply']:.0%}" for l in c["legs"]))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
