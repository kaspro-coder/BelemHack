"""Usage: python -m defi_risk.sim_report  (reads sim/out-scenarios, written by forge test)"""
from . import simulation


def main():
    for pos in simulation.run():
        d = pos["decision"]
        print("=" * 100)
        print(f"{pos['name']}  expiry {pos['expiry']}  ({pos['days']:.0f} days)  implied APY {pos['implied_apy']:.2%}"
              + ("   [probabilities: stablecoin cohort used as a proxy]" if pos.get("proxy") else ""))
        print(f"  exit now (AMM only, measured on the fork): ${pos['calm_exit']:,.0f} for {simulation.FUND_PT:,} PT"
              f"  -> cost {d['exit_cost']:.3%} vs small-trade price {pos['mark']:.4f}")
        print(f"  carry given up by exiting: {d['carry']:.3%}  (vs T-bill {d['risk_free']:.2%})")
        print(f"\n  Scenario: {pos['driver']}, simulated on the real contracts")
        print(f"  {'severity':>8} {'liquidated':>10} {'seized PT':>12} {'stuck PT':>12} {'bad debt $':>11} "
              f"{'exit in window':>15} {'exit after':>11}")
        for e in pos["events"]:
            print(f"  {e['severity']:8.1%} {e['liquidated']:>10} {e['seized_pt']:>12,.0f} {e['stuck_pt']:>12,.0f} "
                  f"{e['bad_debt']:>11,.0f} {e['exit_in_window']:>15,.0f} "
                  f"{'STUCK' if e['fund_stuck'] else f'{e['exit_after']:,.0f}':>11}")
        print(f"\n  Probability of a persistent move >= d before expiry (cohort):")
        print("   " + "  ".join(f"{s:.1%}: {v['p']:.2%}" for s, v in pos["probabilities"].items()))
        for k, lab in (("lo", "low"), ("p", "central"), ("hi", "high")):
            a = d["at"][k]
            print(f"    at {lab:7}: expected permanent loss {a['expected_loss']:.3%} -> {a['verdict']} ({a['edge']:+.3%})")
        print(f"  VERDICT: {d['verdict']}")
        if pos["stuck_from"] is not None and d["p_stuck"]:
            ps = d["p_stuck"]
            print(f"  LIQUIDITY: the position becomes unsellable from a {pos['stuck_from']:.0%} move; "
                  f"chance before expiry {ps['p']:.2%} (range {ps['lo']:.2%} to {ps['hi']:.2%})")
        print(f"  ACTION: watch {pos['trigger']}.")
        print(f"          Exit window once it fires: {pos['window']}.")


if __name__ == "__main__":
    main()
