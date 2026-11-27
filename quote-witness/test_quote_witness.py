import unittest
from dataclasses import replace
from random import Random
from benchmark import fixtures, benchmark
from quote_witness import check

class WitnessTests(unittest.TestCase):
    def test_labels(self):
        for family, name, rule, rows, labels in fixtures():
            with self.subTest(family=family, name=name):
                self.assertEqual(check(rule, rows), labels)

    def test_permutation_invariance(self):
        rng = Random(927)
        for _, _, rule, rows, labels in fixtures():
            for _ in range(20):
                rng.shuffle(rows)
                self.assertEqual(check(rule, rows), labels)

    def test_identical_evidence_not_extra_stock(self):
        _, _, rule, rows, _ = next(fixtures())
        self.assertEqual(check(rule, rows[:-1] + [rows[-2]]), ("PASS", "FAIL"))

    def test_unknown_price_holds(self):
        _, _, rule, rows, _ = next(fixtures())
        self.assertEqual(check(rule, rows[:-1] + [replace(rows[-1], price="unknown")]), ("PASS", "HOLD"))

    def test_metamorphic_amendment(self):
        _, _, rule, rows, _ = next(fixtures())
        self.assertEqual(check(replace(rule, allow_bundle=True), rows), check(rule, rows))

    def test_contract_score(self):
        result = benchmark()
        self.assertEqual(result["switch"]["check"]["exact_axes"], 5)
        self.assertEqual(result["storage"]["check"]["exact_axes"], 5)

if __name__ == "__main__":
    unittest.main()
