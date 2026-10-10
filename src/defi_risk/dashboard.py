"""Export live data for the dashboard: python -m defi_risk.dashboard [sUSDe] [2026-11-26]

Writes dashboard/data.json. The page (dashboard/index.html) reads it and recomputes the
stay/exit verdict in the browser when the sliders move.
"""
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import risk, sources
from .discover import discover
from .report import build_book

OUT = Path(__file__).resolve().parents[2] / "dashboard" / "data.json"
CURVE_SIZES = (1e5, 2.5e5, 5e5, 1e6, 1.5e6, 2e6, 3e6, 4e6)


def export(name="sUSDe", expiry="2026-11-26"):
    g = discover(name, expiry)
    book = build_book(name, expiry)
    history = [p for _, p in sources.usde_price_history()]
    curve = [[s, book.curve.cost(s)] for s in CURVE_SIZES if s < book.capacity_usd]
    lending = next(n for n in g.nodes.values() if n.kind == "lending")
    oracle = next((n for n in g.nodes.values() if n.kind == "oracle" and "primary" in n.data), None)
    return {
        "asof": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "position": {"name": f"PT-{name}", "expiry": expiry, "days": book.days_to_expiry,
                     "implied_apy": book.implied_apy, "pt_usd": book.curve.pt_usd},
        "capacity": book.capacity_usd,
        "curve": curve,
        "scenarios": [risk.scenario(book, d) for d in risk.SCENARIOS],
        "params": {"yield_shock": risk.YIELD_SHOCK, "alt_yield": risk.ALT_YIELD,
                   "tail_alpha": risk.TAIL_ALPHA, "sizes": list(risk.SCENARIOS), "p3": 0.01},
        "borrowers": sorted(
            ({"hf": p["healthFactor"], "debt": p["state"]["borrowAssetsUsd"],
              "coll": p["state"]["collateralUsd"]} for p in book.positions),
            key=lambda b: b["hf"]),
        "lending": lending.data,
        "oracle": oracle.data if oracle else None,
        "wobble": {"d1": risk.wobble_frequency(history, book.days_to_expiry, 0.01),
                   "d3": risk.wobble_frequency(history, book.days_to_expiry, 0.03)},
        "graph": {"nodes": [asdict(n) for n in g.nodes.values()],
                  "edges": [asdict(e) for e in g.edges]},
    }


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "sUSDe"
    expiry = sys.argv[2] if len(sys.argv) > 2 else "2026-11-26"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(export(name, expiry), indent=1), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
