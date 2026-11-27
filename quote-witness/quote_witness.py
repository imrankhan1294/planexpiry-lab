"""Offline quote gate for typed, normalized evidence. No purchases or network."""
from dataclasses import dataclass
from collections import Counter

@dataclass(frozen=True)
class Unit:
    serial: str
    sku: str
    slot: str  # chassis ID, "loose", "reference", or "unknown"
    price: str = "none"  # separate, bundled, none, unknown

@dataclass(frozen=True)
class Rule:
    chassis: tuple[str, ...]
    installed: frozenset[str]
    per_chassis: int
    spare: str
    min_spares: int
    allow_bundle: bool = False

def check(rule, rows):
    """A disputed physical identity is conservatively held on both axes."""
    seen = {}
    for row in rows:
        if row.serial in seen and seen[row.serial] != row:
            return ("HOLD", "HOLD")
        seen[row.serial] = row
    units = tuple(seen.values())
    counts = Counter(u.slot for u in units if u.sku in rule.installed)
    wrong = any(u.slot in rule.chassis and u.sku not in rule.installed for u in units)
    deficit = sum(max(0, rule.per_chassis - counts[x]) for x in rule.chassis)
    unknown_fit = sum(u.slot == "unknown" and u.sku in rule.installed for u in units)
    cfg = (
        "FAIL" if wrong or deficit > unknown_fit or any(counts[x] > rule.per_chassis for x in rule.chassis)
        else "HOLD" if deficit or unknown_fit
        else "PASS"
    )
    eligible = {"separate", "bundled"} if rule.allow_bundle else {"separate"}
    spares = [u for u in units if u.sku == rule.spare]
    proved = sum(u.slot == "loose" and u.price in eligible for u in spares)
    maybe = sum(
        (u.slot == "unknown" and u.price in eligible | {"unknown"})
        or (u.slot == "loose" and u.price == "unknown")
        for u in spares
    )
    buy = "PASS" if proved >= rule.min_spares else "HOLD" if proved + maybe >= rule.min_spares else "FAIL"
    return cfg, buy

def sku_totals(rule, rows):
    """Blind pooling; assumes every primary-compatible unit can be allocated."""
    primary = sum(u.sku in rule.installed for u in rows)
    need = len(rule.chassis) * rule.per_chassis
    spare = sum(u.sku == rule.spare for u in rows)
    if rule.spare in rule.installed:
        spare -= need
    return ("PASS" if primary >= need else "FAIL", "PASS" if spare >= rule.min_spares else "FAIL")

def flat_bom(rule, rows):
    """Knows installed demand and listed price grouping, not physical assignment."""
    cfg, _ = sku_totals(rule, rows)
    eligible = {"separate", "bundled"} if rule.allow_bundle else {"separate"}
    count = sum(u.sku == rule.spare and u.price in eligible for u in rows)
    return cfg, "PASS" if count >= rule.min_spares else "FAIL"

def decision(axes):
    return "FAIL" if "FAIL" in axes else "HOLD" if "HOLD" in axes else "PASS"
