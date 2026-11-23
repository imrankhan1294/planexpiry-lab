import concurrent.futures
import random
import unittest
from fractions import Fraction

from demo import COSTS, NAMES, eligible, model
from expiry_gate import LabGate
from planexpiry import Policy, benchmark, optimal

def make_gate():
    p = Policy(("approval", "available"), lambda x: x["approval"] and x["available"],
               (1, 1), (1, 1, 1, 1))
    g = LabGate("synthetic-reschedule:42", p)
    g.record("approval", True, 12)
    g.record("available", True, 10)
    return g

class GateTests(unittest.TestCase):
    def test_expired_is_unknown(self):
        g = make_gate()
        self.assertEqual(g.commit("synthetic-reschedule:42", g.snapshot(), now_tick=10), "HOLD")

    def test_checked_version_and_exact_action(self):
        g = make_gate()
        old = g.snapshot()
        self.assertEqual(g.commit("synthetic-reschedule:43", old, now_tick=9), "HOLD_WRONG_ACTION")
        g.record("approval", False, 12)
        self.assertEqual(g.commit("synthetic-reschedule:42", old, now_tick=9), "HOLD_STALE_SNAPSHOT")
        self.assertEqual(g.commit("synthetic-reschedule:42", g.snapshot(), now_tick=9), "DENY")

    def test_only_one_mock_receipt_across_simulated_threads(self):
        g = make_gate()
        evidence = g.snapshot()
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            results = list(ex.map(lambda _: g.commit("synthetic-reschedule:42", evidence, now_tick=9), range(16)))
        self.assertEqual(results.count("MOCK_RECEIPT_RECORDED"), 1)
        self.assertEqual(results.count("HOLD_ALREADY_RECORDED"), 15)

    def test_benchmark_exact(self):
        p = Policy(NAMES, eligible, COSTS, model(False))
        res = benchmark(p, 5, model(True))
        self.assertEqual(res["training_adaptive"]["resolved"], 1)
        self.assertEqual(res["validation_fixed"]["resolved"], Fraction(11, 25))
        self.assertEqual(res["validation_adaptive"]["resolved"], 1)
        self.assertLess(benchmark(p, 3, model(True))["validation_adaptive"]["resolved"], 1)

    def test_weight_scaling_does_not_change_declared_plan(self):
        rng = random.Random(42)
        for _ in range(20):
            v = tuple(rng.randrange(1, 6) for _ in range(64))
            a = optimal(Policy(NAMES, eligible, COSTS, v), 4)
            b = optimal(Policy(NAMES, eligible, COSTS, tuple(7*x for x in v)), 4)
            self.assertEqual(a, b)

if __name__ == "__main__":
    unittest.main()
