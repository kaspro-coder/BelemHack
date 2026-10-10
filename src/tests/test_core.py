"""Unit tests for the pure computations behind the numbers. Run: cd src && python -m unittest -v"""
import math
import unittest

from defi_risk import cohort, simulation
from defi_risk.discover import contagion_paths, reach, shared_dependencies
from defi_risk.graph import Graph, Node


class Episodes(unittest.TestCase):
    def test_counts_each_persistent_run_once(self):
        prices = [1, 0.96, 0.96, 0.96, 1, 0.96, 0.96, 1]
        self.assertEqual(cohort.episodes(prices, 0.03, min_run=2), 2)

    def test_ignores_single_sample_dips(self):
        self.assertEqual(cohort.episodes([1, 0.9, 1, 0.9, 1], 0.03, min_run=2), 0)

    def test_threshold_is_inclusive(self):
        self.assertEqual(cohort.episodes([0.97, 0.97], 0.03, min_run=2), 1)


class PoissonInterval(unittest.TestCase):
    def test_zero_events_has_zero_lower_bound(self):
        lo, hi = cohort.poisson_ci(0)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, -math.log(0.05), places=3)  # 90% two-sided: upper = -ln(0.05)

    def test_known_values_for_two_events(self):
        lo, hi = cohort.poisson_ci(2)  # Garwood 90%: [0.3554, 6.2958]
        self.assertAlmostEqual(lo, 0.3554, places=3)
        self.assertAlmostEqual(hi, 6.2958, places=3)

    def test_large_counts_do_not_overflow(self):
        lo, hi = cohort.poisson_ci(400)
        self.assertLess(lo, 400)
        self.assertGreater(hi, 400)


class BaseRate(unittest.TestCase):
    def test_rate_is_episodes_per_window(self):
        coins = [{"mechanism": "crypto-backed", "circulating": 1e9, "prices": [1] * 50 + [0.9] * 3 + [1] * 47}]
        r = cohort.base_rate(coins, 0.05, window_days=70, mechanism_filter=None)
        windows = 100 * cohort.PERIOD_DAYS / 70
        self.assertEqual(r["episodes"], 1)
        self.assertAlmostEqual(r["p"], 1 / windows)

    def test_filters_by_size_and_mechanism(self):
        coins = [{"mechanism": "fiat-backed", "circulating": 1e9, "prices": [0.5] * 40},
                 {"mechanism": "crypto-backed", "circulating": 1e6, "prices": [0.5] * 40}]
        r = cohort.base_rate(coins, 0.03, 46, lambda m: m != "fiat-backed", min_circulating=1e8)
        self.assertEqual(r["coins"], 0)


class ExpectedLoss(unittest.TestCase):
    def test_buckets_sum_probability_times_severity(self):
        probs = {0.01: {"p": 0.10}, 0.05: {"p": 0.02}}
        # P(1% <= d < 5%) = 0.08 at 1%, P(d >= 5%) = 0.02 at 5%
        self.assertAlmostEqual(simulation.expected_loss(probs, "p"), 0.08 * 0.01 + 0.02 * 0.05)

    def test_non_monotone_input_never_goes_negative(self):
        probs = {0.01: {"p": 0.01}, 0.05: {"p": 0.02}}
        self.assertGreaterEqual(simulation.expected_loss(probs, "p"), 0)


class Decision(unittest.TestCase):
    def _pos(self, apy, calm_exit=1_000_000):
        return {"days": 73, "calm_exit": calm_exit, "mark": 1.0, "implied_apy": apy, "stuck_from": None}

    def test_high_carry_stays_low_carry_exits(self):
        probs = {0.03: {"p": 0.01, "lo": 0.005, "hi": 0.02}}
        self.assertEqual(simulation.decide(self._pos(0.20), probs, 0.04)["verdict"], "STAY")
        self.assertEqual(simulation.decide(self._pos(0.04), probs, 0.04)["verdict"], "EXIT")

    def test_costly_exit_favours_staying(self):
        probs = {0.03: {"p": 0.01, "lo": 0.005, "hi": 0.02}}  # expected loss 0.03% < 1% exit cost
        self.assertEqual(simulation.decide(self._pos(0.04, calm_exit=990_000), probs, 0.04)["verdict"], "STAY")

    def test_unclear_when_range_straddles(self):
        pos = self._pos(0.04 + 0.0003 * 365 / 73)  # carry 0.03%
        probs = {0.03: {"p": 0.0, "lo": 0.0, "hi": 1.0}}
        pos["calm_exit"] = 1_000_000  # no exit cost
        self.assertEqual(simulation.decide(pos, probs, 0.04)["verdict"], "UNCLEAR")


class GraphWalks(unittest.TestCase):
    def setUp(self):
        g = Graph()
        for nid, kind in (("pt:a", "position"), ("pt:b", "position"), ("lending:morpho:m1", "lending"),
                          ("lending:morpho:m2", "lending"), ("amm:a", "amm"), ("protocol:morpho-blue", "protocol")):
            g.add_node(Node(nid, kind, nid))
        g.add_node(Node("vault:v", "vault", "V", {"total_assets_usd": 10.0, "allocations": {
            "m1": {"market": "M1", "usd": 4.0, "share_of_vault": 0.4, "share_of_market_supply": 0.5},
            "m2": {"market": "M2", "usd": 6.0, "share_of_vault": 0.6, "share_of_market_supply": 0.9}}}))
        g.add_edge("pt:a", "amm:a", "exits_through")
        g.add_edge("lending:morpho:m1", "pt:a", "holds_as_collateral")
        g.add_edge("lending:morpho:m2", "pt:b", "holds_as_collateral")
        for m in ("m1", "m2"):
            g.add_edge(f"lending:morpho:{m}", "protocol:morpho-blue", "runs_on")
            g.add_edge("vault:v", f"lending:morpho:{m}", "lends_into")
        self.g = g

    def test_reach_walks_collateral_and_vault_edges_backwards(self):
        r = reach(self.g, "pt:a")
        self.assertIn("lending:morpho:m1", r)
        self.assertIn("vault:v", r)
        self.assertNotIn("pt:b", r)

    def test_shared_dependencies(self):
        shared = shared_dependencies(self.g)
        self.assertEqual(set(shared), {"vault:v", "protocol:morpho-blue"})

    def test_contagion_path_through_vault(self):
        paths = contagion_paths(self.g)
        self.assertEqual(len(paths), 1)
        self.assertEqual({leg["position"] for leg in paths[0]["legs"]}, {"pt:a", "pt:b"})


class SimulationOutputs(unittest.TestCase):
    """Sanity checks on the committed fork results."""

    def test_susde_stuck_from_one_percent(self):
        self.assertEqual(simulation.susde()["stuck_from"], 0.01)

    def test_short_dips_do_not_switch_the_oracle(self):
        rows = simulation.load("short_dip")
        self.assertTrue(all(not r["switched"] for r in rows if r["hours_depegged"] < 16))
        self.assertTrue(any(r["switched"] for r in rows if r["hours_depegged"] >= 16))

    def test_susde_pt_panic_never_moves_the_oracle(self):
        self.assertTrue(all(r["oracle_after"] == r["oracle_before"] for r in simulation.load("pt_panic")))


if __name__ == "__main__":
    unittest.main()
