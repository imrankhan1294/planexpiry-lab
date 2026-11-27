import json
from dataclasses import replace
from quote_witness import Rule, Unit, check, decision, flat_bom, sku_totals

def fixtures():
    switches = Rule(tuple("ABCDE"), frozenset({"P"}), 2, "F", 5)
    def power(slots): return [Unit(f"p{i}", "P", s) for i, s in enumerate(slots)]
    def fans(slot, price): return [Unit(f"f{i}", "F", slot, price) for i in range(5)]
    balanced = power("AABBCCDDEE")
    yield "switch", "loose", switches, balanced + fans("loose", "separate"), ("PASS", "PASS")
    yield "switch", "reference", switches, balanced + fans("reference", "separate"), ("PASS", "FAIL")
    yield "switch", "unallocated", switches, balanced + fans("unknown", "separate"), ("PASS", "HOLD")
    yield "switch", "pooled PSU", switches, power("AAABBBCCDD") + fans("loose", "separate"), ("FAIL", "PASS")
    alt = [replace(balanced[0], sku="P-alt")] + balanced[1:]
    yield "switch", "prohibited alternate", switches, alt + fans("loose", "separate"), ("FAIL", "PASS")

    storage = Rule(tuple("WXYZ"), frozenset({"C"}), 2, "C", 1)
    controllers = [Unit(f"c{i}", "C", s) for i, s in enumerate("WWXXYYZZ")]
    boxed = Unit("c8", "C", "loose", "separate")
    bundled = replace(boxed, price="bundled")
    amended = replace(storage, allow_bundle=True)
    yield "storage", "boxed spare", storage, controllers + [boxed], ("PASS", "PASS")
    yield "storage", "bundled not allowed", storage, controllers + [bundled], ("PASS", "FAIL")
    yield "storage", "bundled approved", amended, controllers + [bundled], ("PASS", "PASS")
    yield "storage", "allocation unresolved", amended, controllers + [replace(bundled, slot="unknown")], ("HOLD", "HOLD")
    yield "storage", "sources disagree", storage, controllers + [boxed, replace(boxed, slot="reference")], ("HOLD", "HOLD")

def benchmark():
    cases = list(fixtures())
    output = {}
    for family in ("switch", "storage"):
        output[family] = {}
        for gate in (sku_totals, flat_bom, check):
            counts = dict(exact_axes=0, unsafe_accept=0, false_reject=0, hold=0, unresolved_rejected=0)
            for kind, name, rule, rows, labels in cases:
                if kind != family:
                    continue
                axes = gate(rule, rows)
                actual, expected = decision(axes), decision(labels)
                counts["exact_axes"] += axes == labels
                counts["unsafe_accept"] += actual == "PASS" and expected != "PASS"
                counts["false_reject"] += actual == "FAIL" and expected == "PASS"
                counts["hold"] += actual == "HOLD"
                counts["unresolved_rejected"] += actual == "FAIL" and expected == "HOLD"
            output[family][gate.__name__] = counts
    return output

if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2, sort_keys=True))
