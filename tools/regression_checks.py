"""Regression / reproducibility / packaging checks. Appends raw JSONL entries.

Usage: python -I -B tools/regression_checks.py <package_copy_dir> <zip_path> <evidence_dir_to_inspect> <raw_log.jsonl>
The package directory MUST be a disposable copy: its own unit tests may write into it.
"""

import datetime
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import zipfile
from pathlib import Path

LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def entry(check_id, status, **kw):
    return {"suite": "regression", "id": check_id, "criterion": "regression", "status": status, **kw}


def g1_unit_suite(pkg):
    command = [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests"]
    proc = subprocess.run(command, cwd=pkg, capture_output=True, timeout=600)
    err = proc.stderr.decode("utf-8", "replace")
    summary = [line for line in err.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]
    return entry("G1_own_unit_suite_exit_0", "PASS" if proc.returncode == 0 else "FAIL",
                 exit_code=proc.returncode, command=command, cwd=str(pkg), summary=summary,
                 output_sha256=hashlib.sha256(proc.stderr + proc.stdout).hexdigest(), stderr_tail=err[-3000:])


def g2_deterministic(pkg):
    requests = ["2+2는?", "로그인 기능 구현 프롬프트만 작성해줘", "현재 변경을 검수해줘", "검색 기능을 구현해줘",
                "수정하지 마. 분석만 해줘", "배포하지 마. 테스트만 돌려줘", "새 서비스 아이디어를 탐색해줘"]
    code = ("import sys,json; sys.path.insert(0, sys.argv[1]); from harness100.router import route; "
            "print(json.dumps([{k: v for k, v in route(r).items() if k not in ('context',)} for r in json.loads(sys.argv[2])], "
            "ensure_ascii=False, sort_keys=True, default=str))")
    outs = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", code, str(pkg), json.dumps(requests)],
                              capture_output=True, timeout=120)
        outs.append((proc.returncode, hashlib.sha256(proc.stdout).hexdigest()))
    ok = outs[0] == outs[1] and outs[0][0] == 0
    return entry("G2_routing_deterministic_rerun", "PASS" if ok else "FAIL", runs=outs)


def lint_tree(files):
    """files: dict posix_path -> text. Returns list of problems."""
    problems = []
    for name, text in files.items():
        if not name.endswith(".md"):
            continue
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:", target):
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved not in files and not any(k.startswith(resolved.rstrip("/") + "/") for k in files):
                problems.append(f"broken link {name} -> {target}")
        if name.endswith("SKILL.md"):
            if not text.startswith("---\n") or "\n---\n" not in text[4:]:
                problems.append(f"missing frontmatter {name}")
                continue
            header = text[4:].split("\n---\n", 1)[0]
            keys = {line.split(":", 1)[0] for line in header.splitlines() if line and not line.startswith((" ", "\t"))}
            if not {"name", "description"} <= keys:
                problems.append(f"frontmatter keys {sorted(keys)} in {name}")
            m = re.search(r"^name:\s*(\S+)", header, re.M)
            if m and not re.fullmatch(r"[a-z0-9-]{1,64}", m.group(1)):
                problems.append(f"invalid skill name {m.group(1)}")
    return problems


def g3_package_lint(pkg, zip_path):
    problems = []
    files = {p.relative_to(pkg).as_posix(): (p.read_text("utf-8", "replace") if p.suffix == ".md" else "")
             for p in pkg.rglob("*") if p.is_file() and "work" not in p.relative_to(pkg).parts}
    problems += lint_tree(files)
    zinfo = {}
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                problems.append(f"zip CRC error {bad}")
            names = [i.filename for i in z.infolist() if not i.is_dir()]
            tops = {n.split("/", 1)[0] for n in names}
            if len(tops) != 1:
                problems.append(f"zip must contain one top folder, got {sorted(tops)}")
            if any(".." in n.split("/") or "\\" in n for n in names):
                problems.append("unsafe zip entry path")
            zfiles = {n: z.read(n).decode("utf-8", "replace") for n in names}
            problems += [f"zip: {p}" for p in lint_tree(zfiles)]
            zinfo = {"entries": len(names), "top": sorted(tops),
                     "sha256": hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()}
    except (OSError, zipfile.BadZipFile) as error:
        problems.append(f"zip unreadable: {error}")
    return entry("G3_package_links_frontmatter_zip", "PASS" if not problems else "FAIL",
                 problems=problems, zip=zinfo, zip_path=str(zip_path))


def g4_failures_preserved(evidence_dir):
    evidence_dir = Path(evidence_dir)
    found = []
    for p in sorted(evidence_dir.rglob("*")):
        if p.is_file() and p.suffix in (".json", ".jsonl", ".log", ".txt"):
            text = p.read_text("utf-8", "replace")
            if re.search(r'"(?:status|result)":\s*"FAIL"|FAILED \(|"code":\s*[1-9]', text):
                found.append(p.name)
    return entry("G4_failure_records_preserved", "PASS" if found else "FAIL", files_with_failures=found)


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    pkg, zip_path, evidence_dir, log_path = Path(argv[0]).resolve(), Path(argv[1]), Path(argv[2]), argv[3]
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(log_path, "a", encoding="utf-8") as log:
        for fn in (lambda: g1_unit_suite(pkg), lambda: g2_deterministic(pkg),
                   lambda: g3_package_lint(pkg, zip_path), lambda: g4_failures_preserved(evidence_dir)):
            try:
                result = fn()
            except Exception as error:  # a crashing check is a FAIL, never silently skipped
                result = entry("crash", "FAIL", error=repr(error))
            result["time"] = stamp
            log.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            print(f"{result['status']:4}  {result['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
