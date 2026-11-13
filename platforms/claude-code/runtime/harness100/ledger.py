"""Task-wide validation ledger stored outside the project (P1-2).

- One store per machine/user: $HARNESS100_STATE_DIR or %LOCALAPPDATA%/harness100/state (~/.local/state/harness100).
- The file for a task is derived from the *normalised* task id (NFKC, trimmed, casefolded, collapsed
  whitespace) — callers cannot choose a ledger path, so "new ledger file" bypasses are impossible.
- Each line is hash-chained to the previous one; a registry (also chained) lists every task ever seen,
  so a deleted or truncated task ledger is detected instead of silently restarting at zero.
- Writes take an exclusive lock file. If the store is unreadable, inconsistent or locked, recording is
  refused and status reports enforced=False — the limit is never claimed without a working store.
Residual risk: deleting the *entire* store directory cannot be detected locally (needs an external anchor).
"""

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

MAX_ROUNDS = 3  # one initial validation + at most two revalidations
STATUSES = {"PASS", "FAIL", "미검증"}


class LedgerError(RuntimeError):
    pass


class LimitReached(LedgerError):
    pass


def default_state_dir():
    if os.environ.get("HARNESS100_STATE_DIR"):
        return Path(os.environ["HARNESS100_STATE_DIR"])
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "harness100" / "state" if base else Path.home() / ".local" / "state" / "harness100"


def normalize_task_id(task_id):
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id is required")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", task_id).strip()).casefold()


def _line_hash(prev, payload):
    return hashlib.sha256((prev + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")).hexdigest()


class LedgerStore:
    def __init__(self, state_dir=None):
        self.root = Path(state_dir) if state_dir else default_state_dir()
        self.dir = self.root / "ledger"
        self.registry = self.root / "registry.jsonl"
        self.lock = self.root / "ledger.lock"

    # ---- integrity ----
    @staticmethod
    def _read_chain(path):
        entries, prev = [], "genesis"
        if not path.exists():
            return entries
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            stored = row.pop("hash", None)
            if row.get("prev") != prev or _line_hash(prev, row) != stored:
                raise LedgerError(f"hash chain broken in {path.name} line {number}")
            entries.append(row)
            prev = stored
        return entries

    @staticmethod
    def _append(path, payload):
        entries_prev = "genesis"
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                entries_prev = json.loads(lines[-1])["hash"]
        payload = dict(payload, prev=entries_prev)
        payload["hash"] = _line_hash(entries_prev, payload)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _key(self, task_id):
        return hashlib.sha256(normalize_task_id(task_id).encode("utf-8")).hexdigest()

    def _check_consistency(self):
        registered = {row["task"] for row in self._read_chain(self.registry)}
        if self.dir.exists():
            present = {p.stem for p in self.dir.glob("*.jsonl")}
            if present - registered:
                raise LedgerError("ledger files exist that are not in the registry (registry tampered or deleted)")
        return registered

    def rounds(self, task_id):
        key = self._key(task_id)
        registered = self._check_consistency()
        path = self.dir / f"{key}.jsonl"
        if key in registered and not path.exists():
            raise LedgerError("task ledger was deleted; refusing to restart the count")
        return self._read_chain(path)

    def status(self, task_id):
        try:
            rounds = self.rounds(task_id)
        except (LedgerError, OSError, ValueError) as error:
            return {"enforced": False, "reason": str(error), "rounds": None, "remaining_revalidations": None}
        used_reval = max(0, len(rounds) - 1)
        return {"enforced": True, "store": str(self.root), "rounds": rounds,
                "remaining_revalidations": max(0, MAX_ROUNDS - 1 - used_reval) if rounds else MAX_ROUNDS - 1}

    # ---- writes ----
    def _acquire(self, timeout=10.0):
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise LedgerError("ledger lock busy; limit cannot be enforced right now")
                time.sleep(0.05)

    def record(self, task_id, status, evidence=None, note=""):
        if status not in STATUSES:
            raise ValueError("Invalid status")
        evidence_hash = None
        if status in {"PASS", "FAIL"}:
            if not evidence:
                raise ValueError("Observed outcomes require evidence")
            try:
                data = Path(evidence).read_bytes()
            except OSError as error:
                raise ValueError(f"Evidence file unavailable: {error}") from error
            if not data:
                raise ValueError("Evidence file is empty")
            evidence_hash = hashlib.sha256(data).hexdigest()
        self._acquire()
        try:
            key = self._key(task_id)
            rounds = self.rounds(task_id)
            if len(rounds) >= MAX_ROUNDS:
                raise LimitReached("Task-wide revalidation limit reached (1 initial + 2 revalidations)")
            self.dir.mkdir(parents=True, exist_ok=True)
            if not rounds:
                self._append(self.registry, {"task": key, "time": datetime.now().astimezone().isoformat()})
            entry = {"seq": len(rounds), "kind": "initial" if not rounds else "revalidation", "status": status,
                     "evidence": str(evidence) if evidence else None, "evidence_sha256": evidence_hash,
                     "note": note, "time": datetime.now().astimezone().isoformat()}
            self._append(self.dir / f"{key}.jsonl", entry)
            return entry
        finally:
            try:
                os.remove(self.lock)
            except OSError:
                pass
