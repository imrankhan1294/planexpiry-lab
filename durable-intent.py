"""Synthetic SQLite crash matrix for an agent's final write; POSIX, no network."""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

POLICIES = ("fresh-key", "durable-intent", "split-receipt")
FAULTS = ("none", "before-effect-commit", "after-effect-commit", "after-receipt")


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA synchronous=FULL")
    return db


def crash():
    os.kill(os.getpid(), signal.SIGKILL)


def initialize(root):
    with connect(root / "caller.db") as db:
        db.execute("CREATE TABLE intents(task TEXT PRIMARY KEY, token TEXT NOT NULL)")
    with connect(root / "provider.db") as db:
        db.execute("CREATE TABLE effects(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE receipts(token TEXT PRIMARY KEY, payload TEXT NOT NULL, effect_id INTEGER NOT NULL)")


def attempt(root, policy, fault, payload):
    key = uuid.uuid4().hex
    if policy != "fresh-key":
        # Persist the token before dispatch, keyed by an upstream durable task ID.
        with connect(root / "caller.db") as db:
            db.execute("INSERT OR IGNORE INTO intents VALUES (?, ?)", ("task-1", key))
            key = db.execute("SELECT token FROM intents WHERE task=?", ("task-1",)).fetchone()[0]

    with connect(root / "provider.db") as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT payload,effect_id FROM receipts WHERE token=?", (key,)).fetchone()
        if previous:
            return ["replay", previous[1]] if previous[0] == payload else ["conflict", None]

        effect_id = db.execute("INSERT INTO effects(payload) VALUES (?)", (payload,)).lastrowid
        if fault == "before-effect-commit":
            crash()
        if policy == "split-receipt":
            # Deliberately unsafe control: a real effect can outlive its absent receipt.
            db.commit()
            if fault == "after-effect-commit":
                crash()
        db.execute("INSERT INTO receipts VALUES (?, ?, ?)", (key, payload, effect_id))
        db.commit()
        if fault in ("after-effect-commit", "after-receipt"):
            crash()
        return ["commit", effect_id]


def worker(root, policy, fault="none", payload="synthetic action"):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker",
         str(root), policy, fault, payload], capture_output=True, text=True, timeout=10,
    )
    if fault != "none":
        if result.returncode != -signal.SIGKILL or result.stdout:
            raise RuntimeError(f"Expected SIGKILL, got {result!r}")
        return None
    result.check_returncode()
    return json.loads(result.stdout)


def count(root, table):
    if table not in ("effects", "receipts"):
        raise ValueError(table)
    with connect(root / "provider.db") as db:
        return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


def experiment():
    rows = []
    for fault in FAULTS:
        for policy in POLICIES:
            with tempfile.TemporaryDirectory(prefix="planexpiry-") as temp:
                root = Path(temp)
                initialize(root)
                worker(root, policy, fault)
                before = count(root, "effects")
                recovered = worker(root, policy)
                # When the first attempt returned normally, the control is a
                # deliberate replay of an acknowledged request, not a required retry.
                effects = count(root, "effects")
                receipts = count(root, "receipts")
                duplicate = (policy == "fresh-key" and fault != "before-effect-commit"
                             or policy == "split-receipt" and fault == "after-effect-commit")
                assert effects == 1 + int(duplicate)
                assert before == (0 if fault == "before-effect-commit" else 1)
                assert receipts == (1 if policy != "fresh-key" else effects)
                if policy != "fresh-key":
                    assert worker(root, policy) == ["replay", recovered[1]]
                    assert worker(root, policy, payload="changed action") == ["conflict", None]
                    assert count(root, "effects") == effects
                rows.append(dict(fault=fault, policy=policy, before=before,
                                 result=recovered[0], receipt_id=recovered[1],
                                 effects=effects, receipts=receipts))
    return rows


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "--worker":
        print(json.dumps(attempt(Path(sys.argv[2]), *sys.argv[3:])))
    elif len(sys.argv) == 1:
        if os.name != "posix":
            raise SystemExit("This experiment requires a POSIX environment.")
        print(json.dumps(experiment(), indent=2))
    else:
        raise SystemExit("Run with no arguments.")
