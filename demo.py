"""Reproducible synthetic case. No carrier API, credentials, or real itinerary."""
import argparse
import json
from planexpiry import Policy, benchmark

NAMES = ("permission_current", "prefer_original_route", "original_slot_available",
         "original_fare_ok", "alternate_slot_available", "alternate_fare_ok")
COSTS = (1, 1, 2, 1, 2, 1)


def eligible(f):
    if not f["permission_current"]:
        return False
    if f["prefer_original_route"]:
        return f["original_slot_available"] and f["original_fare_ok"]
    return f["alternate_slot_available"] and f["alternate_fare_ok"]


def model(shifted):
    probabilities = (8, 3, 4, 7, 9, 7) if shifted else (9, 7, 9, 9, 4, 6)
    result = []
    for w in range(64):
        weight = 1
        for i, p in enumerate(probabilities):
            weight *= p if w & (1 << i) else 10 - p
        result.append(weight)
    return tuple(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, choices=range(sum(COSTS)+1), default=5)
    args = parser.parse_args()
    result = benchmark(Policy(NAMES, eligible, COSTS, model(False)), args.budget, model(True))
    result["budget"] = args.budget
    print(json.dumps(result, indent=2, default=lambda x: str(x)))


if __name__ == "__main__":
    main()
