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

## Where the guarantees stop

- **Planning:** Exact dynamic programming maximizes expected resolution, then minimizes expected verification cost under the supplied priors. Those weights affect the order only.
- **Decision:** A partial view proves a verdict only when every logically possible completion agrees. A zero probability does not mean false or impossible. If the budget runs out and evidence is incomplete, the result is **HOLD**.
- **Final check:** [expiry_gate.py](expiry_gate.py) is a single-process mock. It rechecks the exact action label, state revision and fact expiry before recording one mock receipt. It has no durable state, trusted clock, identity service or remote effect. Do not use it as production authorization. For a real integration, the authoritative service would have to enforce the relevant preconditions at its own write boundary.
- **Scale:** The exact planner is capped at eight Boolean facts. The exhaustive fixed-order comparison is capped at six. Check costs, availability and shifts here are synthetic assumptions; none of the numbers establish production latency or safety.

The research contribution here is the runnable comparison and failure cases, not a claim of inventing adaptive evaluation or concurrency control. Background: [stochastic Boolean function evaluation](https://arxiv.org/abs/1303.0726) and [HTTP conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).
