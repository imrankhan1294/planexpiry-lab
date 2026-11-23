"""In-memory version fence for the simulator. Records a mock receipt; no external effect."""
from dataclasses import dataclass
from threading import Lock

from planexpiry import Policy, evaluate


@dataclass(frozen=True)
class Evidence:
    value: bool
    expires_at_tick: int


@dataclass(frozen=True)
class Snapshot:
    revision: int
    facts: tuple[tuple[str, Evidence], ...]


class LabGate:
    """One action label and one authoritative toy state. Time is caller-supplied logical time."""

    def __init__(self, action: str, policy: Policy):
        self._action, self._policy = action, policy
        self._state: dict[str, Evidence] = {}
        self._version = 0
        self._completed = False
        self._lock = Lock()

    def record(self, key: str, value: bool, expires_at_tick: int):
        if key not in self._policy.names or type(value) is not bool or type(expires_at_tick) is not int:
            raise ValueError("Invalid evidence.")
        with self._lock:
            self._state[key] = Evidence(value, expires_at_tick)
            self._version += 1

    def _current(self):
        return Snapshot(self._version, tuple(sorted(self._state.items())))

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._current()

    def commit(self, action: str, evidence: Snapshot, *, now_tick: int) -> str:
        """Never execute anything; model the final comparison and mock receipt atomically."""
        if type(now_tick) is not int:
            raise ValueError("Expected logical integer time.")
        with self._lock:
            if action != self._action:
                return "HOLD_WRONG_ACTION"
            if self._completed:
                return "HOLD_ALREADY_RECORDED"
            if evidence != self._current():
                return "HOLD_STALE_SNAPSHOT"
            current = {k: v.value for k, v in evidence.facts if now_tick < v.expires_at_tick}
            status = evaluate(self._policy, current)
            if status != "ALLOW":
                return status
            self._completed = True
            return "MOCK_RECEIPT_RECORDED"
