"""Task-wide validation ledger stored outside the project (P1-2, v3.0.2).

- One store: $HARNESS100_STATE_DIR or %LOCALAPPDATA%/harness100/state (~/.local/state/harness100).
- The ledger file name derives from the *normalised* task id: NFKC, Unicode format characters (Cf: zero-width
  space, soft hyphen, bidi marks, BOM) removed, whitespace collapsed, leading './' and trailing '.', '/', '\\'
  trimmed, casefolded. Callers cannot choose a path, so a "new ledger" cannot reset the count.
- Every ledger line is hash-chained. The registry (also chained) records, after every write, the task's
  record count and last hash. A ledger that is shorter, empty, edited, renamed or deleted no longer matches
  the registry and is reported as tampering (enforced=False); recording is refused instead of restarting.
- Corrupt files raise LedgerError with a clean message (never a raw parser traceback).
Residual risk: rewriting BOTH files consistently, deleting the whole store, or restoring an old copy of it
cannot be detected locally; that needs an external anchor (e.g. the hash pinned by the user elsewhere).
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
    if not isinstance(task_id, str):
        raise ValueError("task_id must be a string")
    text = unicodedata.normalize("NFKC", task_id)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(?:\.[/\\])+", "", text).rstrip("./\\ ").strip()
    if not text:
        raise ValueError("task_id is required")
    return text.casefold()


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
        """Return (entries, last_hash). Raises LedgerError on any corruption."""
        entries, prev = [], "genesis"
        if not path.exists():
            return entries, prev
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise LedgerError(f"cannot read {path.name}: {type(error).__name__}") from error
        for number, raw in enumerate(raw_lines, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError as error:
                raise LedgerError(f"corrupt line {number} in {path.name}") from error
            if not isinstance(row, dict):
                raise LedgerError(f"corrupt line {number} in {path.name}")
            stored = row.pop("hash", None)
            if row.get("prev") != prev or _line_hash(prev, row) != stored:
                raise LedgerError(f"hash chain broken in {path.name} line {number}")
            entries.append(row)
            prev = stored
        return entries, prev

    def _append(self, path, payload):
        _, prev = self._read_chain(path)
        payload = dict(payload, prev=prev)
        payload["hash"] = _line_hash(prev, payload)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return payload["hash"]

    def _key(self, task_id):
        return hashlib.sha256(normalize_task_id(task_id).encode("utf-8")).hexdigest()

    def _registry_state(self):
        rows, _ = self._read_chain(self.registry)
        latest = {}
        for row in rows:
            latest[row.get("task")] = row
        if self.dir.exists():
            present = {p.stem for p in self.dir.glob("*.jsonl")}
            if present - set(latest):
                raise LedgerError("ledger files exist that are not in the registry (registry tampered or deleted)")
        return latest

    def rounds(self, task_id):
        key = self._key(task_id)
        latest = self._registry_state()
        path = self.dir / f"{key}.jsonl"
        entries, last = self._read_chain(path)
        expected = latest.get(key)
        if expected is None:
            if entries:
                raise LedgerError("task ledger exists without a registry record")
            return entries
        if not path.exists():
            raise LedgerError("task ledger was deleted; refusing to restart the count")
        if expected.get("count") != len(entries) or expected.get("last") != last:
            raise LedgerError(f"task ledger does not match the registry (expected {expected.get('count')} records, "
                              f"found {len(entries)}): truncated or edited")
        return entries

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
            entry = {"seq": len(rounds), "kind": "initial" if not rounds else "revalidation", "status": status,
                     "evidence": str(evidence) if evidence else None, "evidence_sha256": evidence_hash,
                     "note": note, "time": datetime.now().astimezone().isoformat()}
            last = self._append(self.dir / f"{key}.jsonl", entry)
            self._append(self.registry, {"task": key, "count": len(rounds) + 1, "last": last,
                                         "time": datetime.now().astimezone().isoformat()})
            return entry
        finally:
            try:
                os.remove(self.lock)
            except OSError:
                pass
