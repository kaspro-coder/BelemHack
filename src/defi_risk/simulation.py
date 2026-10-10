"""Decision layer fed by the Anvil fork simulations (sim/out-scenarios/*.jsonl).

For each position it answers three questions with measured numbers:
  1. stay or exit: carry given up vs expected permanent loss vs the real cost of exiting now;
  2. liquidity risk: the chance the position becomes unsellable before maturity;
  3. action plan: which signal to watch, and how long the fund has to exit once it fires.

Probabilities come from the stablecoin cohort (cohort.py), never from a human input.
For PT-reUSD the cohort is a proxy: a NAV write-down by the issuer is treated like a
persistent depeg of a comparable non-fiat dollar token.
"""
import json
import math
from itertools import groupby
from pathlib import Path

from . import cohort, sources

OUT = Path(__file__).resolve().parents[2] / "sim" / "out-scenarios"
FUND_PT = 1_000_000  # the simulated position, in PT
SEVERITIES = (0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.20)


def load(name):
    return [json.loads(l) for l in (OUT / f"{name}.jsonl").read_text().splitlines() if l.strip()]


def _apy(ln_rate):
    return math.exp(ln_rate / 1e18) - 1


def susde():
    base = load("baseline")
    meta, exits = base[0], base[1:]
    depeg = load("usde_depeg")
    mark = exits[0]["exit_usd"] / 1e6 / (exits[0]["exit_pt"] / 1e18)
    stuck = [r for r in depeg if r["fund_unsold_after"] > 0]
    return {
        "name": "PT-sUSDe", "expiry": "2026-11-26",
        "days": (meta["expiry"] - meta["timestamp"]) / 86400,
        "implied_apy": _apy(meta["ln_implied_rate"]),
        "mark": mark,
        "calm_exit": depeg[0]["fund_exit_calm"] / 1e6,
        "exit_curve": [(r["exit_pt"] / 1e18, r["exit_usd"] / 1e6, r["unsold_pt"] / 1e18) for r in exits],
        "driver": "USDe depeg (Chainlink USDe/USD)",
        "stuck_from": min(r["depeg_bps"] for r in stuck) / 1e4 if stuck else None,
        "window": "16 h",
        "window_hours": meta["challenge_timelock"] / 3600,
        "trigger": f"USDe/USD below {1 - meta['threshold'] / 1e18:.4f} (oracle deviation threshold "
                   f"{meta['threshold'] / 1e16:.2f}%): the challenge can start, liquidations follow "
                   f"{meta['challenge_timelock'] / 3600:.0f} h later",
        "events": [{
            "severity": r["depeg_bps"] / 1e4, "liquidated": r["liquidated"],
            "seized_pt": r["seized_pt"] / 1e18, "stuck_pt": r["unsold_pt"] / 1e18,
            "bad_debt": r["bad_debt_usdc"] / 1e6,
            "exit_in_window": r["fund_exit_t0"] / 1e6, "exit_after": r["fund_exit_after"] / 1e6,
            "fund_stuck": r["fund_unsold_after"] > 0,
        } for r in depeg],
        "events_prudent": [{
            "severity": r["depeg_bps"] / 1e4, "liquidated": r["liquidated"], "skipped": r["skipped"],
            "seized_pt": r["seized_pt"] / 1e18, "debt_at_risk": r["debt_at_risk"] / 1e6,
            "underwater": r["underwater"] / 1e6, "exit_after": r["fund_exit_after"] / 1e6,
            "fund_stuck": r["fund_unsold"] > 0,
        } for r in load("usde_depeg_prudent")],
        "short_dip": load("short_dip"),
        "feed_failure": load("feed_failure"),
        "pt_panic": load("pt_panic"),
    }


def reusd():
    base = load("reusd_baseline")
    meta, exits = base[0], base[1:]
    mark = exits[0]["exit_asset"] / 1e6 / (exits[0]["exit_pt"] / 1e6)
    events = []
    for bps, rounds in groupby(load("reusd_writedown"), key=lambda r: r["shock_pt"]):
        rounds = list(rounds)
        events.append({
            "severity": bps / 1e4, "rounds": len(rounds) - 1,
            "liquidated": sum(r["liquidated"] for r in rounds),
            "seized_pt": sum(r["seized_pt"] for r in rounds) / 1e6,
            "stuck_pt": rounds[-1]["unsold_pt"] / 1e6,
            "bad_debt": sum(r["bad_debt"] for r in rounds) / 1e6,
            "exit_in_window": rounds[0]["fund_exit"] / 1e6, "exit_after": rounds[-1]["fund_exit"] / 1e6,
            "fund_stuck": rounds[-1]["fund_unsold"] > 0,
            "oracle_path": [r["oracle_price"] / 1e36 for r in rounds],
        })
    panic = []
    for shock, rounds in groupby(load("reusd_cascade"), key=lambda r: r["shock_pt"]):
        rounds = list(rounds)
        panic.append({"dump_pt": shock / 1e6, "liquidated": sum(r["liquidated"] for r in rounds),
                      "oracle_low": min(r["oracle_price"] for r in rounds) / 1e36,
                      "oracle_start": rounds[0]["oracle_price"] / 1e36,
                      "fund_exit": rounds[-1]["fund_exit"] / 1e6, "apy_after": _apy(rounds[-1]["ln_implied_rate"])})
    prudent = []
    for bps, rounds in groupby(load("reusd_writedown_prudent"), key=lambda r: r["cut_bps"]):
        rounds = list(rounds)
        last = rounds[-1]
        prudent.append({"severity": bps / 1e4, "liquidated": sum(r["liquidated"] for r in rounds),
                        "skipped": last["skipped"], "seized_pt": sum(r["seized_pt"] for r in rounds) / 1e6,
                        "debt_at_risk": last["debt_at_risk"] / 1e6, "underwater": last["underwater"] / 1e6,
                        "exit_after": last["fund_exit"] / 1e6,
                        # PT left unsold, or a few thousand dollars out of ~$980k: either way not an exit
                        "fund_stuck": last["fund_unsold"] > 0 or last["fund_exit"] < 100_000})
    stuck = [e for e in events if e["fund_stuck"]]
    return {
        "name": "PT-reUSD", "expiry": "2026-12-10",
        "days": (meta["expiry"] - meta["timestamp"]) / 86400,
        "implied_apy": _apy(meta["ln_implied_rate"]),
        "mark": mark,
        "calm_exit": load("reusd_cascade")[0]["fund_exit_calm"] / 1e6,
        "exit_curve": [(r["exit_pt"] / 1e6, r["exit_asset"] / 1e6, r["unsold_pt"] / 1e6) for r in exits],
        "driver": "reUSD NAV write-down (re.xyz share price)",
        "stuck_from": min(e["severity"] for e in stuck) if stuck else None,
        "window": "15 min",
        "window_hours": 0.25,
        "trigger": "re.xyz getSharePrice() falls: the oracle's 15-minute TWAP passes it on, "
                   "liquidations follow within one TWAP period",
        "borrowers": meta["borrowers_usdc"] + meta["borrowers_usdt"],
        "events": events,
        "pt_panic": panic,
        "events_prudent": prudent,
        "proxy": True,
    }


def contagion():
    """Smokehouse USDT run on the PT-sUSDS/USDT market (sim/test/SusdsContagion.t.sol)."""
    return [{"step": r["step"], "hours": r["hours"], "utilization": r["utilization"] / 1e18,
             "borrow_apr": r["borrow_apr"] / 1e18, "liquidity": r["liquidity"] / 1e6,
             "vault_locked": r["vault_assets"] / 1e6, "pt_apy": _apy(r["pt_ln_implied_rate"])}
            for r in load("susds_contagion")]


def reusd_bad_debt_by_market():
    out = {}
    for bps, rounds in groupby(load("reusd_writedown"), key=lambda r: r["shock_pt"]):
        rounds = list(rounds)
        out[bps / 1e4] = {"usdc": sum(r["bad_debt_usdc_mkt"] for r in rounds) / 1e6,
                          "usdt": sum(r["bad_debt_usdt_mkt"] for r in rounds) / 1e6}
    return out


def susds():
    base = load("susds_baseline")
    meta, exits = base[0], base[1:]
    depeg = load("susds_depeg")
    mark = exits[0]["exit_usd"] / 1e6 / (exits[0]["exit_pt"] / 1e18)
    stuck = [r for r in depeg if r["fund_unsold_after"] > 0]
    calm = load("susds_baseline")[3]["exit_usd"] / 1e6  # the 1M PT sale
    return {
        "name": "PT-sUSDS", "expiry": "2026-11-26",
        "days": (meta["expiry"] - meta["timestamp"]) / 86400,
        "implied_apy": _apy(meta["ln_implied_rate"]),
        "mark": mark, "calm_exit": calm,
        "exit_curve": [(r["exit_pt"] / 1e18, r["exit_usd"] / 1e6, r["unsold_pt"] / 1e18) for r in exits],
        "driver": "USDS depeg (Chainlink USDS/USD)",
        "stuck_from": min(r["severity"] for r in stuck) / 1e4 if stuck else None,
        "window": "16 h", "window_hours": meta["challenge_timelock"] / 3600,
        "trigger": f"USDS/USD below {1 - meta['threshold'] / 1e18:.4f} (deviation threshold {meta['threshold'] / 1e16:.2f}%): "
                   f"challenge, then liquidations {meta['challenge_timelock'] / 3600:.0f} h later",
        "events": [{
            "severity": r["severity"] / 1e4, "liquidated": r["liquidated"], "seized_pt": r["seized_pt"] / 1e18,
            "stuck_pt": r["unsold_pt"] / 1e18, "bad_debt": r["bad_debt"] / 1e6,
            "exit_in_window": r["fund_exit_t0"] / 1e6, "exit_after": r["fund_exit_after"] / 1e6,
            "fund_stuck": r["fund_unsold_after"] > 0,
        } for r in depeg],
        "pt_panic": [{"dump_pt": r["severity"] / 1e18, "liquidated": r["liquidated"],
                      "oracle_start": r["oracle_start"] / 1e24, "oracle_low": r["oracle_low"] / 1e24,
                      "apy_after": _apy(r["ln_implied_rate"]), "fund_exit": r["fund_exit_after"] / 1e6,
                      "fund_stuck": r["fund_unsold_after"] > 0} for r in load("susds_panic")],
        "oracle_note": "Ojo returns the lower of the Pendle 15-min TWAP and a conservative feed: the market "
                       "must first fall below that floor before the oracle moves.",
    }


def crowd(name, pt_unit):
    """Fund exit inside the window when `crowd_pt` PT from others reach the pool first."""
    rows = [{"crowd_pt": r["crowd_pt"] / pt_unit, "severity": r["severity_bps"] / 1e4,
             "fund_exit": r["fund_exit"] / 1e6, "fund_unsold": r["fund_unsold"] / pt_unit} for r in load(name)]
    first = min(r["severity"] for r in rows)
    rows = [r for r in rows if r["severity"] == first]
    room = max((r["crowd_pt"] for r in rows if r["fund_unsold"] == 0), default=0.0)
    blocked = min((r["crowd_pt"] for r in rows if r["fund_unsold"] > 0), default=None)
    return {"severity": first, "rows": rows, "room_pt": room, "blocked_from_pt": blocked}


def probabilities(days):
    """P(persistent depeg >= d within the holding window) per severity, with 90% ranges."""
    prices = cohort.load_prices()
    nonfiat = lambda m: m != "fiat-backed"
    return {d: cohort.base_rate(prices, d, days, nonfiat, 1e8) for d in SEVERITIES}


def expected_loss(probs, level):
    """Expected permanent loss: sum over severity buckets of P(bucket) x severity."""
    sizes = sorted(probs)
    total = 0.0
    for i, d in enumerate(sizes):
        nxt = probs[sizes[i + 1]][level] if i + 1 < len(sizes) else 0.0
        total += max(0.0, probs[d][level] - nxt) * d
    return total


def decide(pos, probs, risk_free):
    T = pos["days"] / 365
    exit_cost = 1 - pos["calm_exit"] / (FUND_PT * pos["mark"])
    carry = (pos["implied_apy"] - risk_free) * T
    at = {}
    for level in ("lo", "p", "hi"):
        loss = expected_loss(probs, level)
        edge = carry - loss + exit_cost
        at[level] = {"expected_loss": loss, "edge": edge, "verdict": "STAY" if edge > 0 else "EXIT"}
    verdicts = {a["verdict"] for a in at.values()}
    verdict = verdicts.pop() if len(verdicts) == 1 else "UNCLEAR"
    stuck_from = pos["stuck_from"]
    p_stuck = {k: probs[stuck_from][k] for k in ("lo", "p", "hi")} if stuck_from in probs else None
    prudent = [e["severity"] for e in pos.get("events_prudent", []) if e["fund_stuck"]]
    pos["stuck_from_prudent"] = min(prudent) if prudent else None
    p_stuck_prudent = ({k: probs[pos["stuck_from_prudent"]][k] for k in ("lo", "p", "hi")}
                       if pos["stuck_from_prudent"] in probs else None)
    return {"verdict": verdict, "at": at, "exit_cost": exit_cost, "carry": carry, "risk_free": risk_free,
            "p_stuck": p_stuck, "p_stuck_prudent": p_stuck_prudent}


def run():
    rf = sources.risk_free_rate()
    out = []
    crowds = {"PT-sUSDe": crowd("crowd_exit", 1e18), "PT-reUSD": crowd("reusd_crowd_exit", 1e6),
              "PT-sUSDS": crowd("susds_crowd_exit", 1e18)}
    for pos in (susde(), reusd(), susds()):
        pos["crowd"] = crowds[pos["name"]]
        probs = probabilities(round(pos["days"]))
        pos["probabilities"] = {d: {k: v[k] for k in ("p", "lo", "hi", "episodes", "coins")} for d, v in probs.items()}
        pos["decision"] = decide(pos, probs, rf)
        out.append(pos)
    return out
