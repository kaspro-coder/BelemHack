"""Export everything the dashboard shows: python -m defi_risk.dashboard

Writes dashboard/data.json from
  * the fork simulations (sim/out-scenarios, produced by `forge test` on the Anvil fork),
  * the multi-token dependency graph (live discovery),
  * the cohort probabilities and the exchange-hack base rate.
"""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import portfolio, simulation, venues
from .discover import contagion_paths, discover_many, shared_dependencies

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "data.json"
TOKENS = [("sUSDe", "2026-11-26"), ("reUSD", "2026-12-10"), ("sUSDS", "2026-11-26")]


def export():
    positions = simulation.run()
    book = portfolio.build(positions)
    for p in positions:
        p["probabilities"] = {f"{d:g}": v for d, v in p["probabilities"].items()}
    g = discover_many(TOKENS)
    shared = shared_dependencies(g)
    hack = venues.incident_rate(round(positions[0]["days"]))
    block = ROOT / "data" / "fork_block.txt"
    return {
        "asof": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "fork_block": int(block.read_text().strip()) if block.exists() else None,
        "fund_pt": simulation.FUND_PT,
        "positions": positions,
        "graph": {"nodes": [asdict(n) for n in g.nodes.values()], "edges": [asdict(e) for e in g.edges]},
        "shared": shared,
        "contagion": {"paths": contagion_paths(g), "vault_run": simulation.contagion(),
                      "reusd_bad_debt": {f"{k:g}": v for k, v in simulation.reusd_bad_debt_by_market().items()}},
        "book": book,
        "exchange_hacks": {k: hack[k] for k in ("incidents", "exchange_years", "per_year", "lo", "hi")},
    }


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(export(), indent=1, default=str), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
