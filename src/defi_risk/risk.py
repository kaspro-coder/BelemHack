"""Scenario engine and stay/exit decision for a PT-sUSDe position.

Chain of effects for a USDe depeg of size d:
  1. direct loss on the PT (it redeems into USDe) plus a rate shock;
  2. Morpho borrowers whose health factor falls below 1 get liquidated;
  3. liquidators dump the seized PT into the Pendle pool, pushing the price down further.

Every number marked ASSUMPTION is a judgement, not a measurement. The decision is also
reported as a break-even probability so the reader does not have to trust our prior.
"""
from dataclasses import dataclass

from . import sources

# ASSUMPTION: a depeg widens the PT discount: yield shock (annualised) = YIELD_SHOCK * d.
YIELD_SHOCK = 5.0
# Opportunity cost of cash if we exit: the measured US 3-month T-bill yield (Book.risk_free).
# ASSUMPTION: P(permanent depeg >= d before expiry) = p3 * (0.03 / d) ** TAIL_ALPHA.
# No permanent USDe depeg appears in 3 years of history, so this tail is a judgement.
TAIL_ALPHA = 1.0
SCENARIOS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.10)


@dataclass
class Book:
    positions: list  # Morpho borrowers: health factor, debt, collateral (USD)
    curve: object  # ExitCurve
    capacity_usd: float
    days_to_expiry: float
    implied_apy: float
    risk_free: float


def liquidated_collateral(positions, x):
    """USD collateral seized when the oracle price of the PT falls by fraction x."""
    return sum(p["state"]["collateralUsd"] for p in positions if p["healthFactor"] * (1 - x) < 1)


def scenario(book, d):
    duration = book.days_to_expiry / 365
    x = d + duration * YIELD_SHOCK * d  # oracle-visible fall of the PT price after failover
    seized = liquidated_collateral(book.positions, x)
    sellable = min(seized, book.capacity_usd)
    impact = book.curve.cost(sellable) if sellable else 0.0
    return {
        "depeg": d, "pt_price_fall": x, "seized_usd": seized,
        "unsellable_usd": max(0.0, seized - book.capacity_usd),
        "cascade_impact": impact or 0.0,
        "holder_loss": x + (impact or 0.0),
    }


def empirical_exceedance(history, window_days, d):
    """Share of rolling windows in which USDe traded at or below 1-d at least once."""
    prices = history
    n = len(prices) - window_days
    hits = sum(1 for i in range(n) if min(prices[i:i + window_days]) <= 1 - d)
    return hits / n


def permanent_exceedance(d, p3):
    return min(1.0, p3 * (0.03 / d) ** TAIL_ALPHA)


def expected_loss(p3, sizes=SCENARIOS):
    """Expected PERMANENT loss for a holder to maturity: the depeg itself, if it persists.

    Rate shocks and forced-sale price impact are mark-to-market only: the PT converges
    to par at expiry, so they cost a holder who is not forced to sell nothing at maturity.
    """
    total = 0.0
    for i, d in enumerate(sizes):
        nxt = permanent_exceedance(sizes[i + 1], p3) if i + 1 < len(sizes) else 0.0
        total += max(0.0, permanent_exceedance(d, p3) - nxt) * d
    return total


def decide(book, size_usd, p3):
    T = book.days_to_expiry / 365
    exit_cost = book.curve.cost(size_usd)
    excess_carry = (book.implied_apy - book.risk_free) * T
    e_loss = expected_loss(p3)
    edge = excess_carry - e_loss + exit_cost  # >0 means staying beats exiting
    lo, hi = 0.0, 1.0  # break-even p3 by bisection (expected loss is increasing in p3)
    for _ in range(50):
        mid = (lo + hi) / 2
        if excess_carry - expected_loss(mid) + exit_cost > 0:
            lo = mid
        else:
            hi = mid
    return {
        "verdict": "STAY" if edge > 0 else "EXIT", "edge": edge, "exit_cost": exit_cost,
        "excess_carry": excess_carry, "expected_loss": e_loss, "p3": p3, "breakeven_p3": lo,
    }


def wobble_frequency(history, window_days, d):
    """Share of rolling windows where USDe touched 1-d at least once (mark-to-market risk)."""
    n = len(history) - window_days
    return sum(1 for i in range(n) if min(history[i:i + window_days]) <= 1 - d) / n


def triggers(book):
    """Live early-warning levels worth monitoring."""
    worst = min(book.positions, key=lambda p: p["healthFactor"])
    return {
        "largest_borrower_distance_to_liquidation": 1 - 1 / worst["healthFactor"],
        "largest_borrower_debt_usd": worst["state"]["borrowAssetsUsd"],
    }


def market_implied_p3(book):
    """Tail probability at which expected loss equals the excess yield the market pays.

    It is an upper bound on what the market prices for this risk: the spread also pays
    for liquidity and smart-contract risk.
    """
    carry = (book.implied_apy - book.risk_free) * book.days_to_expiry / 365
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if expected_loss(mid) < carry else (lo, mid)
    return lo


def robust_decision(book, size_usd, estimate):
    """Verdict from data only. STAY or EXIT only if the whole 90% range agrees."""
    at = {k: decide(book, size_usd, estimate[k]) for k in ("lo", "p", "hi")}
    verdicts = {v["verdict"] for v in at.values()}
    if verdicts == {"STAY"}:
        verdict = "STAY"
    elif verdicts == {"EXIT"}:
        verdict = "EXIT"
    else:
        verdict = "UNCLEAR"
    return {"verdict": verdict, "central": at["p"]["verdict"], "at": at,
            "market_p3": market_implied_p3(book)}
