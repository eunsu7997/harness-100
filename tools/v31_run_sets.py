"""Run a v3.1-CC probe set (usability / set D) through the real hook as a subprocess. See evidence/v31/SCORING.md.

usage: python -I -B tools/v31_run_sets.py <set.jsonl> <expected_sha256> <out_results.jsonl>
Prints a JSON summary. Never modifies the set file (hash checked before running).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HOOK = PKG / "hooks" / "claude_code_hook.py"


def judge(expect, decision):
    return {"allow": decision == "allow", "defer": decision == "defer", "deny": decision == "deny",
            "not_allow": decision != "allow", "not_deny": decision != "deny", "any": True}[expect]


def main(argv):
    set_path, sha, out_path = Path(argv[0]), argv[1], Path(argv[2])
    raw = set_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != sha:
        raise SystemExit(f"hash mismatch: {actual}")
    items = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    work = Path(tempfile.mkdtemp(prefix="h100-v31-sets-"))
    env = dict(os.environ, HARNESS100_HOOK_STATE=str(work / "state"))

    def call(payload):
        proc = subprocess.run([sys.executable, "-I", "-B", str(HOOK)], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              capture_output=True, env=env, timeout=60)
        out = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0:
            return "error:" + str(proc.returncode)
        if not out:
            return "defer"
        data = json.loads(out)["hookSpecificOutput"]
        return data.get("permissionDecision", "defer") if payload["hook_event_name"] == "PreToolUse" else "ctx"

    rows = []
    for item in items:
        project = work / ("p-" + item["id"])
        (project / "src").mkdir(parents=True, exist_ok=True)
        session = "sess-" + item["id"]
        for turn in item["turns"]:
            call({"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": turn, "cwd": str(project)})
        for k, probe in enumerate(item["probes"]):
            decision = call({"hook_event_name": "PreToolUse", "session_id": session, "tool_name": probe["tool"],
                             "tool_input": probe["input"], "permission_mode": item.get("mode", "default"), "cwd": str(project)})
            rows.append({"id": item["id"], "probe": k, "category": item["category"], "mode": item.get("mode", "default"),
                         "tool": probe["tool"], "input": probe["input"], "expect": probe["expect"], "decision": decision,
                         "match": judge(probe["expect"], decision) if not decision.startswith("error") else False,
                         "turns": item["turns"]})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    total = len(rows)
    matched = sum(r["match"] for r in rows)
    g1 = [r for r in rows if r["decision"] == "allow" and r["expect"] not in ("allow", "any")]
    want_allow = [r for r in rows if r["expect"] == "allow"]
    reconfirm = [r for r in want_allow if r["decision"] != "allow"]
    normal = [r for r in rows if r["expect"] in ("allow", "defer", "not_deny")]
    rejected = [r for r in normal if r["decision"] == "deny"]
    errors = [r for r in rows if r["decision"].startswith("error")]
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], [0, 0])
        c[0] += r["match"]
        c[1] += 1
    summary = {"set": set_path.name, "sha256": actual, "items": len(items), "probes": total, "matched": matched,
               "match_rate": round(matched / total, 4) if total else None, "G1_allow_outside_grant": len(g1),
               "reconfirm": [len(reconfirm), len(want_allow)], "rejected": [len(rejected), len(normal)],
               "errors": len(errors), "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_cat.items()},
               "results": str(out_path)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
