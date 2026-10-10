"""Export live data for the dashboard: python -m defi_risk.dashboard [sUSDe] [2026-11-26]

Writes dashboard/data.json. The page (dashboard/index.html) reads it and recomputes the
stay/exit verdict in the browser when the sliders move.
"""
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import cohort, risk, sources, venues
from .discover import discover
from .report import build_book

OUT = Path(__file__).resolve().parents[2] / "dashboard" / "data.json"
CURVE_SIZES = (1e5, 2.5e5, 5e5, 1e6, 1.5e6, 2e6, 3e6, 4e6)


def export(name="sUSDe", expiry="2026-11-26"):
    g = discover(name, expiry)
    book = build_book(name, expiry)
    history = [p for _, p in sources.usde_price_history()]
    est = cohort.estimate_p3(book.days_to_expiry)
    prices = cohort.load_prices()
    tiers = []
    for label, mc in (("all sizes", 0), ("> $10M", 1e7), ("> $100M", 1e8), ("> $1B", 1e9)):
        t = cohort.base_rate(prices, 0.03, book.days_to_expiry, lambda m: m != "fiat-backed", mc)
        tiers.append({"label": label, **{k: t[k] for k in ("coins", "episodes", "p", "lo", "hi")}})
    vr = venues.incident_rate(book.days_to_expiry)
    n_venues = sum(1 for n in g.nodes.values() if n.kind == "perp_venue")
    vs = risk.scenario(book, venues.PRECEDENT_DEPEG)
    venue = {"incidents": vr["incidents"], "exchange_years": vr["exchange_years"], "per_year": vr["per_year"],
             "lo": vr["lo"], "hi": vr["hi"], "n_venues": n_venues,
             "p_any": venues.prob_any(vr["per_year"], n_venues, book.days_to_expiry),
             "p_any_lo": venues.prob_any(vr["lo"], n_venues, book.days_to_expiry),
             "p_any_hi": venues.prob_any(vr["hi"], n_venues, book.days_to_expiry),
             "depeg": venues.PRECEDENT_DEPEG, "scenario": vs,
             "seized_without_rate_shock": risk.liquidated_collateral(book.positions, venues.PRECEDENT_DEPEG)}
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
        "params": {"yield_shock": risk.YIELD_SHOCK, "risk_free": book.risk_free,
                   "tail_alpha": risk.TAIL_ALPHA, "sizes": list(risk.SCENARIOS)},
        "estimate": est, "tiers": tiers, "venue": venue, "market_p3": risk.market_implied_p3(book),
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
