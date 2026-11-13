"""Quality gate that scores only what it executes itself (P1-1).

- Report/score files are never inputs. `evaluate_claims_file` exists to prove that: it always accepts 0 claims.
- `run_gate` copies the package to a temp dir, runs tools/adversarial_checks.py and tools/regression_checks.py
  as subprocesses, keeps the raw JSONL it produced, and scores it with the fixed catalog.
- Checks the gate cannot run (platform installs) stay 미검증. Missing checks are 미검증, never PASS.
- `suite_sha256` fingerprints tests/ + tools/ + harness100/ so a reviewer can pin it; changing the
  checks themselves is detectable only against a pinned value held outside the agent's reach.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def _catalog_module(package=PACKAGE):
    spec = importlib.util.spec_from_file_location("h100_score", Path(package) / "tools" / "score_from_log.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def suite_sha256(package=PACKAGE):
    h = hashlib.sha256()
    for folder in ("harness100", "tests", "tools", "hooks"):
        for path in sorted((Path(package) / folder).rglob("*.py")):
            h.update(path.relative_to(package).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def evaluate_claims_file(path):
    """A score/report file is a claim. It is read only to report that it was rejected."""
    try:
        size = Path(path).stat().st_size
    except OSError:
        size = None
    return {"total": 0, "accepted_claims": 0, "claims_file": str(path), "claims_file_size": size,
            "reason": "Report files are never accepted as evidence; run the gate to execute the checks"}


def score_rows(rows, catalog, weights=None):
    """Score rows the gate itself produced. Absent IDs are 미검증; FAIL rows are kept in the output."""
    weights = weights or {name: 100 / len(catalog) for name in catalog}
    by_id = {row["id"]: row for row in rows}
    table, total, fails, unverified = [], 0.0, 0, 0
    for criterion, ids in catalog.items():
        share = weights[criterion] / len(ids)
        statuses = [by_id.get(cid, {}).get("status", "미검증") for cid in ids]
        statuses = [s if s in ("PASS", "FAIL", "미검증") else "FAIL" for s in statuses]
        earned = share * statuses.count("PASS")
        total += earned
        fails += statuses.count("FAIL")
        unverified += statuses.count("미검증")
        table.append({"criterion": criterion, "weight": weights[criterion], "earned": round(earned, 2),
                      "checks": [{"id": cid, "status": s} for cid, s in zip(ids, statuses)]})
    overall = "완전 성공" if not fails and not unverified else "부분 성공" if total > 0 else "실패"
    flat = [c for row in table for c in row["checks"]]
    return {"total": round(total, 2), "overall": overall, "rows": flat, "criteria": table,
            "fail_count": fails, "unverified_count": unverified}


def run_gate(out_dir, package=PACKAGE, zip_path=None, expect_suite=None):
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw = out_dir / f"qgate-raw-{stamp}.jsonl"
    fingerprint = suite_sha256(package)
    with tempfile.TemporaryDirectory(prefix="h100-qgate-") as tmp:
        copy = Path(tmp) / "pkg"
        shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__", "work", "ledger-state"))
        work = Path(tmp) / "work"
        zip_path = zip_path or next(iter(sorted((Path(package) / "dist").glob("*Claude-Chat.zip"))), None)
        commands = [
            [sys.executable, "-I", "-B", str(copy / "tools" / "adversarial_checks.py"), str(copy), str(work), str(raw)],
            [sys.executable, "-I", "-B", str(copy / "tools" / "regression_checks.py"), str(copy),
             str(zip_path or (copy / "missing.zip")), str(Path(package) / "evidence"), str(raw)],
            [sys.executable, "-I", "-B", str(copy / "tools" / "defect_checks.py"), str(copy), str(Path(tmp) / "work-defects"), str(raw)],
        ]
        runs = []
        for command in commands:
            proc = subprocess.run(command, capture_output=True, timeout=1800, cwd=tmp)
            runs.append({"command": command[2], "exit_code": proc.returncode,
                         "stdout_tail": proc.stdout.decode("utf-8", "replace")[-2000:]})
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    catalog_module = _catalog_module(package)
    report = score_rows(rows, catalog_module.CATALOGS["v3.0.2"], catalog_module.WEIGHTS)
    report.update({"raw_log": str(raw), "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                   "suite_sha256": fingerprint, "runner_exit_codes": runs,
                   "suite_pinned": None if expect_suite is None else (expect_suite == fingerprint),
                   "note": "platform checks are not executed by the gate and therefore count as 미검증"})
    if expect_suite is not None and expect_suite != fingerprint:
        report["overall"] = "실패"
        report["total"] = 0
        report["reason"] = "suite fingerprint differs from the pinned value"
    (out_dir / f"qgate-report-{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
