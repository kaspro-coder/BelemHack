"""Usage: python -m defi_risk sUSDe 2026-11-26"""
import sys

from .discover import discover


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "sUSDe"
    expiry = sys.argv[2] if len(sys.argv) > 2 else None
    g = discover(name, expiry)

    print(f"{len(g.nodes)} nodes, {len(g.edges)} edges\n")
    for n in g.nodes.values():
        print(f"[{n.kind:8}] {n.label}")
        for k, v in n.data.items():
            print(f"            {k}: {v:,.4g}" if isinstance(v, float) else f"            {k}: {v}")
    print()
    for e in g.edges:
        exp = f"  (${e.exposure_usd:,.0f})" if e.exposure_usd else ""
        print(f"{g.nodes[e.source].label}  --{e.relation}-->  {g.nodes[e.target].label}{exp}")


main()
