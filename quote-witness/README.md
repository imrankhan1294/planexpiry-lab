# Quote Witness

A purchasing agent sees five fans on a quote. Are those five loose spares, or five references to the fans already installed? The SKU and quantity are identical; the purchase decision should not be.

This offline experiment separates two decisions: **does each chassis have the approved installed parts?** and **does the customer receive the requested, separately priced spares?** Each physical unit has an identity, an allocation and a pricing status. Repeated identical evidence does not create another unit. Ambiguous allocation produces a hold when it could change the outcome. A buyer amendment can permit bundled spares without changing the installed configuration.

## Reproduce

Python 3.10+, standard library only. From this directory:

    python3 -B -m unittest -v
    python3 -B benchmark.py

| Checker | Exact two-axis results | Unsafe accepts | Holds | Unresolved cases rejected |
| --- | ---: | ---: | ---: | ---: |
| Pooled SKU totals | 4 / 10 | 6 | 0 | 0 |
| Flat BOM plus price grouping | 5 / 10 | 5 | 0 | 0 |
| Unit allocation and price evidence | 10 / 10 | 0 | 3 | 0 |

An unsafe accept is an overall pass on an expected failure or hold. The benchmark has five fictional switch scenarios and a separate five-case storage family that uses the same SKU for installed and spare units. Expectations are explicit fixtures, not learned labels. These deliberately selected counterexamples show where the fixed baselines break; they do not estimate real-world error rates.

The pooled baseline reserves installed demand but ignores allocation and price grouping. The flat baseline adds price grouping but still ignores where units are assigned. Neither implements abstention. The evidence-aware checker gives each fixture a per-chassis and commercial result; any definite failure blocks the purchase, otherwise a hold requires clarification.

## Where the result stops

Input is already normalized by a trusted upstream process. This does not extract PDFs, verify evidence provenance, match aliases, convert packs into eaches, verify revisions or recommend suppliers. If two rows disagree about the same unit, both axes are held even if one conflict might be irrelevant. Quote data alone does not prove delivery. A useful next experiment would measure how often reviewed inputs still miss bundle semantics and whether field-level conflict isolation reduces unnecessary holds.

Related prior art: [OASIS UBL 2.3](https://docs.oasis-open.org/ubl/os-UBL-2.3/UBL-2.3.html) models quote and order line semantics; [GS1 packaging hierarchy guidance](https://ref.gs1.org/guidelines/gdm-implementation/) distinguishes eaches, packs, cases and pallets. Quote Witness is a synthetic decision test, not an implementation of either standard.
