# PlanExpiry Lab

**An AI agent's plan can be right when it makes it and wrong when it acts.** This lab explores which facts it should recheck when every check costs time and the agent has a fixed budget.

The example is a fictional reschedule. Before it can proceed, the agent needs current permission and evidence that the selected route still has a slot and an acceptable fare. Checking both routes is wasteful; skipping a necessary check is worse. **The planner chooses what to check. The evidence decides the verdict.**

## Run it in a minute

Python 3.10+, standard library only. No keys, network calls or real accounts.

```sh
python3 demo.py
python3 demo.py --budget 3
python3 -B -m unittest -v
```

[benchmark.json](benchmark.json) contains the default run's exact fractions. The six facts and their costs are in [demo.py](demo.py).

## What the experiment found

Two schedules use **the same policy, facts, observations and hard budget**. The fixed baseline tries all 720 static orders, chooses the best one on the training distribution, and stops as soon as the result is proven. The adaptive method chooses its next check after each answer. Both strategies are frozen before evaluation under the shifted distribution. Every result is an exact weighted calculation over the 64 fictional worlds, not a run on real agent traffic.

| Check budget | Training: fixed / adaptive resolved | Shifted scenario: fixed / adaptive resolved |
| ---: | :--- | :--- |
| 2 | 12.0% / 19.0% | 21.0% / 27.0% |
| 3 | 20.8% / 31.3% | **36.8% / 20.2%** |
| 4 | 27.1% / 36.1% | **44.0% / 39.1%** |
| 5 | 73.0% / 100% | 44.0% / 100% |
| 8 | 100% / 100% | 100% / 100% |

At five units the adaptive schedule can check only the relevant route and still fit the entire required branch. That budget fits by construction in this example. At tighter budgets the trained planner can recheck the wrong thing first under shift, and the fixed order can win. A resolved result includes both **ALLOW** and **DENY**; neither method is credited for guessing.

## Final write boundary experiment

A separate [mock booking experiment](final-write.cjs) asks what happens when a record changes after the last read. Run `node final-write.cjs` for the breakdown and `node final-write.cjs --self-test` for the trace oracle, replay checks, and ordered two-event cases.

In eight deliberately chosen synthetic cases, the global-revision policy committed once and the dependency-scoped policy twice. The extra commit was the case in which someone edited an unrelated record. Neither wrote on stale evidence. A no-write client shadow would have allowed four stale decisions, including a slot that closed and reopened with a new revision. Those are fixture counts, not estimates of reliability or production traffic. Both write policies assume the same authoritative service can atomically validate the slot and approval and persist the receipt alongside the effect.

## When both evidence sources go down together

Run `node evidence-outages.cjs` (Node 18+, no dependencies). The fictional agent can proceed only if current approval and capacity are both true. The two cheapest paths per fact may share an outage. An alternate costs two check units instead of one. All policies have the same five-unit budget and the same decision rule: unavailable evidence never counts as a denial or an approval.

| Evaluation scenario | Fixed, independent | Fixed, dependency-aware | Adaptive, independent | Adaptive, dependency-aware |
| --- | ---: | ---: | ---: | ---: |
| Independent cheap paths | 93.70% | 92.14% | **97.28%** | 90.71% |
| Held out: cheap paths commonly share outages | 80.68% | 83.27% | 80.86% | **91.44%** |
| Held out: nominal fallback often shares the outage too | 80.68% | 80.54% | 80.81% | **81.70%** |
| Held out: common cheap-path outages and more denials | 80.74% | 85.33% | 80.89% | **92.71%** |

Entries are exact weighted ALLOW + DENY rates, rounded for display. The fixed policies search all 720 endpoint orders per training model; adaptive policies search feasible observation-dependent choices, maximizing resolution first and minimizing expected cost on ties. Cheap paths have 80% marginal availability and alternates 70% in all scenarios. The dependency-aware planner trains on a mixture with an 85% chance of a shared cheap-path regime; held-out outage scenarios use 95%. In the fallback-coupled scenario, 85% of worlds also tie alternates to the primary failure domain. The dependency-aware policy spends 2.393 check units on average in the common-outage scenario, versus 2.242 for the independence-trained adaptive policy. It also loses on independent paths. Circuit breakers, real latency, contradictory evidence and final-write consistency are outside this model. The code checks all 256 truth/availability combinations for conclusive correctness and budget compliance.

Related work: [When to Hedge in Interactive Services](https://www.usenix.org/conference/nsdi21/presentation/primorac) studies when redundant requests help or hurt latency. This lab instead measures evidence resolution under an explicit check budget, using synthetic truth and outages.

## What survives a lost acknowledgment?

Run `python3 -B durable-intent.py` on POSIX (Python 3.10+, standard library). Every first attempt and replay runs in a separate process. The harness kills the first worker at a selected SQLite transaction boundary and counts durable mock effects and receipts after restart.

| First attempt | Fresh token on replay | Persisted token + atomic receipt | Persisted token + split receipt |
| --- | ---: | ---: | ---: |
| Acknowledged; deliberate replay | 2 | 1 | 1 |
| Killed before effect commit | 1 | 1 | 1 |
| Killed just after effect commit | 2 | 1 | 2 |
| Killed after receipt commit | 2 | 1 | 1 |

Cells count effects, not requests. In the split-receipt failure there are **two effects and only one receipt**: the first effect committed without its receipt, and recovery ran it again despite reusing the token. With atomic receipts, replay returns the original effect ID when the effect already committed; reusing the token with a different payload returns a conflict. The fresh-token baseline models an agent that regenerates the token after restart, not what a properly idempotent client would do.

These are 12 selected synthetic fixtures, not an estimate of failure rates. The caller assumes the same upstream task ID is recovered and the provider owns the effect and receipt in one durable transaction. The demo does not cover power loss, an external provider without idempotency, or unknown remote status. When a provider cannot prove the outcome, the safe response is to hold for reconciliation, not issue a new token. Related prior art: [AWS Builders’ Library on safe retries](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

## Where the guarantees stop

- **Planning:** Exact dynamic programming maximizes expected resolution, then minimizes expected verification cost under the supplied priors. Those weights affect the order only.
- **Decision:** A partial view proves a verdict only when every logically possible completion agrees. A zero probability does not mean false or impossible. If the budget runs out and evidence is incomplete, the result is **HOLD**.
- **Final check:** [expiry_gate.py](expiry_gate.py) is a single-process mock. It rechecks the exact action label, state revision and fact expiry before recording one mock receipt. It has no durable state, trusted clock, identity service or remote effect. Do not use it as production authorization. For a real integration, the authoritative service would have to enforce the relevant preconditions at its own write boundary.
- **Scale:** The exact planner is capped at eight Boolean facts. The exhaustive fixed-order comparison is capped at six. Check costs, availability and shifts here are synthetic assumptions; none of the numbers establish production latency or safety.

The research contribution here is the runnable comparison and failure cases, not a claim of inventing adaptive evaluation or concurrency control. Background: [stochastic Boolean function evaluation](https://arxiv.org/abs/1303.0726) and [HTTP conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).
