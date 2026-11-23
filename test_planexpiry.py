"""Independent standard-library checks for PlanExpiry's Boolean planning API."""
from fractions import Fraction
from itertools import product
import unittest

from planexpiry import Policy, evaluate, optimal


def all_required(facts):
    return facts["approved"] and facts["fresh"]


class DecisionTests(unittest.TestCase):
    def test_unverified_or_expired_evidence_stays_unknown(self):
        policy = Policy(("approved", "fresh"), all_required, (1, 1), (1, 1, 1, 1))
        # A caller omits stale evidence: neither approval nor time makes it fresh.
        self.assertEqual(evaluate(policy, {"approved": True}), "HOLD")
        self.assertEqual(evaluate(policy, {"approved": True, "fresh": False}), "DENY")
        self.assertEqual(evaluate(policy, {"approved": True, "fresh": True}), "ALLOW")
        self.assertEqual(evaluate(policy, {"approved": False}), "DENY")

    def test_zero_prior_cannot_substitute_for_an_authoritative_check(self):
        policy = Policy(("approved", "fresh"), all_required, (1, 1), (0, 0, 0, 1))
        self.assertEqual(evaluate(policy, {}), "HOLD")
        self.assertEqual(evaluate(policy, {"approved": True}), "HOLD")
        self.assertEqual(evaluate(policy, {"approved": True, "fresh": False}), "DENY")
        plan = optimal(policy, budget=1, observed={"approved": True})
        self.assertEqual(plan.next_check, "fresh")
        self.assertEqual(plan.resolved_probability, Fraction(1))
        self.assertEqual(plan.expected_cost, Fraction(1))

    def test_partial_decision_matches_every_boolean_completion(self):
        names = ("approved", "active", "scope")
        def allowed(facts):
            return facts["approved"] and (facts["active"] or facts["scope"])
        policy = Policy(names, allowed, (1, 1, 1), (0, 1, 3, 0, 0, 4, 0, 0))
        full_worlds = [dict(zip(names, truth)) for truth in product((False, True), repeat=3)]
        for evidence in product((None, False, True), repeat=3):
            partial = {k: v for k, v in zip(names, evidence) if v is not None}
            possibilities = {allowed(w) for w in full_worlds
                             if all(w[k] == v for k, v in partial.items())}
            want = ("ALLOW" if possibilities == {True}
                    else "DENY" if possibilities == {False} else "HOLD")
            with self.subTest(evidence=partial):
                self.assertEqual(evaluate(policy, partial), want)


class OptimizerTests(unittest.TestCase):
    def test_and_optimal_resolves_at_minimum_expected_cost(self):
        policy = Policy(("approved", "fresh"), all_required, (1, 2), (1, 1, 1, 1))
        plan = optimal(policy, budget=3)
        self.assertEqual(plan.next_check, "approved")
        self.assertEqual(plan.resolved_probability, Fraction(1))
        self.assertEqual(plan.expected_cost, Fraction(2))

    def test_cannot_spend_more_than_remaining_budget(self):
        policy = Policy(("approved", "fresh"), all_required, (1, 2), (1, 1, 1, 1))
        plan = optimal(policy, budget=1)
        self.assertEqual(plan.next_check, "approved")
        self.assertEqual(plan.resolved_probability, Fraction(1, 2))
        self.assertEqual(plan.expected_cost, Fraction(1))
        held = optimal(policy, budget=1, observed={"approved": True})
        self.assertIsNone(held.next_check)
        self.assertEqual(held.resolved_probability, Fraction(0))
        self.assertEqual(held.expected_cost, Fraction(0))

    def test_bit_order_and_asymmetric_priors_pick_most_resolving_check(self):
        # Weights at index 1 and 2 correspond respectively to
        # (approved=True,fresh=False) and (approved=False,fresh=True).
        policy = Policy(("approved", "fresh"), all_required, (1, 1), (0, 1, 3, 0))
        plan = optimal(policy, budget=1)
        self.assertEqual(plan.next_check, "approved")
        self.assertEqual(plan.resolved_probability, Fraction(3, 4))
        self.assertEqual(plan.expected_cost, Fraction(1))
        self.assertEqual(evaluate(policy, {"approved": True}), "HOLD")

    def test_already_resolved_does_not_request_or_charge_for_checks(self):
        policy = Policy(("approved", "fresh"), all_required, (1, 2), (1, 1, 1, 1))
        for observed in ({"approved": False}, {"approved": True, "fresh": True}):
            with self.subTest(observed=observed):
                plan = optimal(policy, budget=0, observed=observed)
                self.assertIsNone(plan.next_check)
                self.assertEqual(plan.resolved_probability, Fraction(1))
                self.assertEqual(plan.expected_cost, Fraction(0))


if __name__ == "__main__":
    unittest.main()
