"""Evidence bookkeeping (compatible API with v3.0 MVP, hardened for P1-1 / P1-2)."""

import hashlib
from pathlib import Path
from .ledger import LedgerStore, LimitReached, LedgerError  # noqa: F401  (re-exported)


def check_result(executed, passed, evidence_file=None):
    """Classify one caller-observed check. The caller's booleans are still claims; see qgate for scoring."""
    if type(executed) is not bool or (passed is not None and type(passed) is not bool):
        raise ValueError("executed and passed must be booleans (passed may be None)")
    if not executed or passed is None or evidence_file is None:
        return {"status": "미검증", "reason": "Execution or outcome evidence is missing"}
    try:
        path = Path(evidence_file)
        data = path.read_bytes()
    except OSError:
        return {"status": "미검증", "reason": "Evidence file is unavailable"}
    if not data:
        return {"status": "미검증", "reason": "Evidence file is empty"}
    return {"status": "PASS" if passed else "FAIL", "evidence": str(path.resolve()),
            "sha256": hashlib.sha256(data).hexdigest(),
            "provenance": "caller-asserted; not accepted by the quality gate"}


class ValidationLedger:
    """Facade over the persistent LedgerStore. Constructing a new object never resets the count."""

    def __init__(self, task_id, rounds=None, store=None):
        self.store = store or LedgerStore()
        self.task_id = task_id
        self.store.rounds(task_id)  # validates id and store integrity early

    @property
    def rounds(self):
        return self.store.rounds(self.task_id)

    def record(self, status, evidence):
        return self.store.record(self.task_id, status, evidence)

    def to_dict(self):
        return {"task_id": self.task_id, "rounds": self.rounds}

    @classmethod
    def from_dict(cls, data, store=None):
        # Serialized copies are informational only; the persistent store is authoritative.
        return cls(data["task_id"], store=store)


RUBRIC = {"routing": 25, "safety": 25, "regression": 20, "evidence": 15, "platforms": 15}


def score_report(checks):
    """Caller-asserted checks earn nothing (P1-1). Use `python -m harness100 qgate` to score from execution."""
    rows = []
    for name, weight in RUBRIC.items():
        claim = check_result(**{k: v for k, v in checks.get(name, {"executed": False, "passed": None}).items()
                                if k in ("executed", "passed", "evidence_file")}) if name in checks else \
            {"status": "미검증", "reason": "No check supplied"}
        rows.append({"criterion": name, "weight": weight, "earned": 0, "claimed_status": claim["status"],
                     "status": "미검증", "reason": "Caller assertions are not execution evidence"})
    return {"total": 0, "maximum": 100, "criteria": rows, "overall": "미검증",
            "note": "Scores are only produced by qgate, which re-executes the checks itself"}
