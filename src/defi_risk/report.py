"""Usage: python -m defi_risk.report [sUSDe] [2026-11-26] [size_usd]"""
import sys
from datetime import datetime, timezone

from . import cohort, risk, sources
from .discover import discover
from .exit_cost import ExitCurve


def build_book(name, expiry):
    g = discover(name, expiry)
    amm = next(n for n in g.nodes.values() if n.kind == "amm")
    market = amm.id.split(":", 1)[1]
    lending = next(n for n in g.nodes.values() if n.kind == "lending")
    curve = ExitCurve(market)
    exp = datetime.fromisoformat(next(n for n in g.nodes.values() if n.kind == "position").label.split("(")[1][:-1]).replace(tzinfo=timezone.utc)
    book = risk.Book(
        positions=sources.morpho_positions(lending.id.split(":")[-1]),
        curve=curve, capacity_usd=curve.capacity_usd(),
        days_to_expiry=(exp - datetime.now(timezone.utc)).days,
        implied_apy=amm.data["implied_apy"], risk_free=sources.risk_free_rate(),
    )
    return book


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "sUSDe"
    expiry = sys.argv[2] if len(sys.argv) > 2 else "2026-11-26"
    size = float(sys.argv[3]) if len(sys.argv) > 3 else 1_000_000
    book = build_book(name, expiry)
    history = [p for _, p in sources.usde_price_history()]
    debt = sum(p["state"]["borrowAssetsUsd"] for p in book.positions)

    print(f"Position: ${size:,.0f} of PT-{name}, {book.days_to_expiry} days to expiry")
    print(f"Pool exit capacity ${book.capacity_usd/1e6:.2f}M | Morpho: {len(book.positions)} borrowers, debt ${debt/1e6:.2f}M\n")
    print("USDe depeg scenarios")
    print(f"{'depeg':>6} {'PT price fall':>14} {'seized $M':>10} {'unsellable $M':>14} {'cascade':>8} {'MTM loss':>12}")
    for d in risk.SCENARIOS:
        s = risk.scenario(book, d)
        print(f"{d:6.1%} {s['pt_price_fall']:14.2%} {s['seized_usd']/1e6:10.2f} "
              f"{s['unsellable_usd']/1e6:14.2f} {s['cascade_impact']:8.2%} {s['holder_loss']:12.2%}")

    est = cohort.estimate_p3(book.days_to_expiry)
    r = risk.robust_decision(book, size, est)
    c = r["at"]["p"]
    print()
    print("Mark-to-market risk (does not hurt a holder to maturity, hurts a forced seller)")
    print(f"  USDe touched -1% in {risk.wobble_frequency(history, book.days_to_expiry, 0.01):.1%} of past {book.days_to_expiry}-day windows,"
          f" -3% in {risk.wobble_frequency(history, book.days_to_expiry, 0.03):.1%}")
    print()
    print("Decision for a holder to maturity (permanent loss only, no human input)")
    print(f"  P(persistent >=3% depeg in {book.days_to_expiry}d), from {est['coins']} comparable stablecoins "
          f"({est['episodes']} episodes): {est['p']:.2%}  (90% range {est['lo']:.2%} to {est['hi']:.2%})")
    print(f"  the market's price of this risk (upper bound):  {r['market_p3']:.2%}")
    print(f"  certain cost of exiting now      {c['exit_cost']:8.3%}")
    print(f"  carry given up by exiting        {c['excess_carry']:8.3%}   (implied {book.implied_apy:.2%} vs T-bill {book.risk_free:.2%}, measured)")
    print(f"  expected permanent loss if stay  {c['expected_loss']:8.3%}   (central estimate)")
    for k, lab in (("lo", "low end"), ("p", "central"), ("hi", "high end")):
        a = r["at"][k]
        print(f"    at {lab:8} ({est[k]:.2%}): {a['verdict']} ({a['edge']:+.3%})")
    print(f"  VERDICT: {r['verdict']}" + ("  (the range does not agree: consider reducing size)" if r["verdict"] == "UNCLEAR" else ""))

    t = risk.triggers(book)
    print()
    print("Early-warning levels")
    print(f"  largest Morpho borrower (${t['largest_borrower_debt_usd']/1e6:.2f}M debt) is "
          f"{t['largest_borrower_distance_to_liquidation']:.2%} from liquidation")


if __name__ == "__main__":
    main()
