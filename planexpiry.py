"""Offline exact budgeted verification, not an authorization or dispatch system."""
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import permutations
from typing import Callable

@dataclass(frozen=True)
class Plan:
    next_check: str | None
    resolved_probability: Fraction
    expected_cost: Fraction

@dataclass(frozen=True)
class Policy:
    names: tuple[str, ...]
    allowed: Callable[[dict[str, bool]], bool]
    costs: tuple[int, ...]
    weights: tuple[int, ...]

    def __post_init__(self):
        n = len(self.names)
        if not 1 <= n <= 8 or len(set(self.names)) != n or any(type(k) is not str or not k for k in self.names):
            raise ValueError("Choose one to eight distinct nonempty fact names.")
        if len(self.costs) != n or any(type(c) is not int or c <= 0 for c in self.costs):
            raise ValueError("Each fact needs a positive integer cost.")
        if len(self.weights) != (1 << n) or any(type(w) is not int or w < 0 for w in self.weights) or not sum(self.weights):
            raise ValueError("Provide a nonnegative integer weight for each world, with some positive weight.")

def _observations(policy, observed):
    if any(k not in policy.names or type(v) is not bool for k, v in observed.items()):
        raise ValueError("Pass only established Boolean facts; omit unknown facts.")
    mask = yes = 0
    for i, name in enumerate(policy.names):
        if name in observed:
            mask |= 1 << i
            yes |= int(observed[name]) << i
    return mask, yes

def _truth(policy):
    result = []
    for w in range(len(policy.weights)):
        verdict = policy.allowed({k: bool(w & (1 << i)) for i, k in enumerate(policy.names)})
        if type(verdict) is not bool:
            raise ValueError("A policy must return a Boolean in every possible world.")
        result.append(verdict)
    return tuple(result)

def _verdict(t, mask, yes):
    found_true = found_false = False
    for w, value in enumerate(t):
        if w & mask == yes:
            found_true |= value
            found_false |= not value
            if found_true and found_false:
                return "HOLD"
    return "ALLOW" if found_true else "DENY"

def evaluate(policy: Policy, observed: dict[str, bool]) -> str:
    """Proof ignores all weights, including zero-weight worlds."""
    return _verdict(_truth(policy), *_observations(policy, observed))

def _weights(policy):
    @lru_cache(None)
    def mass(mask, yes):
        return sum(w for i, w in enumerate(policy.weights) if i & mask == yes)
    return mass

def _budget(budget):
    if type(budget) is not int or budget < 0:
        raise ValueError("Budget must be a nonnegative integer.")

def optimal(policy: Policy, budget: int, observed: dict[str, bool] | None = None) -> Plan:
    """Exact finite-world optimizer: maximize resolution, then minimize expected check cost."""
    _budget(budget)
    mask, yes = _observations(policy, {} if observed is None else observed)
    truth = _truth(policy)
    mass = _weights(policy)
    # If evidence contradicts all training worlds, use a uniform planning fallback.
    if not mass(mask, yes):
        mass = _weights(Policy(policy.names, policy.allowed, policy.costs, (1,) * len(truth)))

    @lru_cache(None)
    def solve(m, y, b):
        if _verdict(truth, m, y) != "HOLD":
            return Plan(None, Fraction(1), Fraction(0))
        best = Plan(None, Fraction(0), Fraction(0))
        total = mass(m, y)
        if not total:
            return best
        for i, (name, price) in enumerate(zip(policy.names, policy.costs)):
            bit = 1 << i
            if m & bit or price > b:
                continue
            prob, cost = Fraction(0), Fraction(price)
            for answer in (0, bit):
                weight = Fraction(mass(m | bit, y | answer), total)
                if not weight:
                    continue
                tail = solve(m | bit, y | answer, b - price)
                prob += weight * tail.resolved_probability
                cost += weight * tail.expected_cost
            if (prob, -cost) > (best.resolved_probability, -best.expected_cost):
                best = Plan(name, prob, cost)
        return best

    return solve(mask, yes, min(budget, sum(policy.costs)))

def benchmark(policy: Policy, budget: int, validation: tuple[int, ...]) -> dict:
    """Select best fixed order and adaptive choices on training weights, evaluate frozen policies."""
    _budget(budget)
    if len(policy.names) > 6:
        raise ValueError("The exhaustive fixed-order baseline is limited to six facts.")
    if len(validation) != 1 << len(policy.names) or any(type(w) is not int or w < 0 for w in validation) or not sum(validation):
        raise ValueError("Invalid validation world weights.")
    truth = _truth(policy)
    classify = lru_cache(None)(lambda m, y: _verdict(truth, m, y))

    def score(run, weights):
        total = sum(weights)
        hold = allow = deny = cost = 0
        for w, weight in enumerate(weights):
            if not weight:
                continue
            v, s = run(w)
            if s > budget or (v == "ALLOW" and not truth[w]) or (v == "DENY" and truth[w]):
                raise AssertionError("Budget or logical proof violated.")
            hold += weight * (v == "HOLD")
            allow += weight * (v == "ALLOW")
            deny += weight * (v == "DENY")
            cost += weight * s
        return {"resolved": Fraction(allow + deny, total), "allow": Fraction(allow, total),
                "deny": Fraction(deny, total), "hold": Fraction(hold, total), "units": Fraction(cost, total)}

    def run_fixed(actual, order):
        m = y = spent = 0
        for i in order:
            if classify(m, y) != "HOLD":
                break
            if spent + policy.costs[i] > budget:
                continue
            spent += policy.costs[i]
            bit = 1 << i
            m |= bit
            y |= actual & bit
        return classify(m, y), spent

    best, metrics = None, None
    for order in permutations(range(len(policy.names))):
        row = score(lambda w: run_fixed(w, order), policy.weights)
        if best is None or (row["resolved"], -row["units"]) > (metrics["resolved"], -metrics["units"]):
            best, metrics = order, row

    @lru_cache(None)
    def decision(facts, remainder):
        return optimal(policy, remainder, dict(facts)).next_check

    def adaptive(actual):
        observed, spent = {}, 0
        for _ in policy.names:
            name = decision(tuple(sorted(observed.items())), budget - spent)
            if name is None:
                break
            if name in observed:
                raise AssertionError("A resolved fact was rechecked.")
            index = policy.names.index(name)
            spent += policy.costs[index]
            observed[name] = bool(actual & (1 << index))
        return evaluate(policy, observed), spent

    return {"fixed_order": tuple(policy.names[i] for i in best),
            "adaptive_first": decision((), budget),
            "training_fixed": metrics, "training_adaptive": score(adaptive, policy.weights),
            "validation_fixed": score(lambda w: run_fixed(w, best), validation),
            "validation_adaptive": score(adaptive, validation)}
