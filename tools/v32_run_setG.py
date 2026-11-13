"""Run the step-based hold-out set G (v3.2) through the real hook as a subprocess.

usage: python -I -B tools/v32_run_setG.py <setG.jsonl> <expected_sha256> <out_results.jsonl>
Placeholders: {P} granting project, {P2} second project, {OUT} folder outside any project, {HOME} the user's home
(used only as a target string: only hook decisions are measured, nothing is written there).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HOOK = PKG / "hooks" / "claude_code_hook.py"


def judge(expect, decision):
    return {"allow": decision == "allow", "defer": decision == "defer", "deny": decision == "deny",
            "not_allow": decision != "allow", "not_deny": decision != "deny", "any": True}[expect]


def subst(value, env):
    if isinstance(value, str):
        for key, real in env.items():
            value = value.replace("{" + key + "}", real)
        return value
    if isinstance(value, dict):
        return {k: subst(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [subst(v, env) for v in value]
    return value


def do_setup(step, env, notes):
    kind, path = step.get("type"), subst(step.get("path", ""), env)
    try:
        if kind == "mkdir":
            Path(path).mkdir(parents=True, exist_ok=True)
        elif kind == "file":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(step.get("content", "x"), encoding="utf-8")
        elif kind == "symlink":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            target = subst(step["target"], env)
            os.symlink(target, path, target_is_directory=Path(target).is_dir())
        elif kind == "junction":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            target = subst(step["target"], env)
            if os.name == "nt":
                import _winapi
                Path(target).mkdir(parents=True, exist_ok=True)
                _winapi.CreateJunction(str(Path(target).resolve()), str(Path(path)))
            else:
                os.symlink(target, path, target_is_directory=True)
        else:
            notes.append(f"unknown setup {kind}")
    except Exception as error:  # e.g. symlink privilege missing on Windows
        notes.append(f"setup {kind} failed: {type(error).__name__}")


def main(argv):
    set_path, sha, out_path = Path(argv[0]), argv[1], Path(argv[2])
    raw = set_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise SystemExit("hash mismatch")
    # split on "\n" only: str.splitlines() would also split on U+2028/U+0085 inside JSON strings
    items = [json.loads(line) for line in raw.decode("utf-8").split("\n") if line.strip()]
    root = Path(tempfile.mkdtemp(prefix="h100-v32-G-"))
    rows = []
    for item in items:
        base = root / item["id"]
        env = {"P": str(base / "proj"), "P2": str(base / "proj2"), "OUT": str(base / "outside"), "HOME": str(Path.home())}
        for key in ("P", "P2", "OUT"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)
        notes = []
        for step in item.get("setup", []):
            do_setup(step, env, notes)
        state = base / "state"
        proc_env = dict(os.environ, HARNESS100_HOOK_STATE=str(state))
        for k, step in enumerate(item["steps"]):
            payload = {"session_id": step.get("session", "S1"), "cwd": subst(step.get("cwd", "{P}"), env)}
            if step["type"] == "prompt":
                payload.update(hook_event_name="UserPromptSubmit", prompt=subst(step["text"], env) if "{" in step["text"] else step["text"])
            else:
                payload.update(hook_event_name="PreToolUse", tool_name=step["tool"], tool_input=subst(step["input"], env),
                               permission_mode=item.get("mode", "default"))
            proc = subprocess.run([sys.executable, "-I", "-B", str(HOOK)], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                  capture_output=True, env=proc_env, timeout=60)
            if step["type"] != "tool":
                continue
            out = proc.stdout.decode("utf-8", "replace").strip()
            if proc.returncode != 0:
                decision = f"error_rc{proc.returncode}"
            elif not out:
                decision = "defer"
            else:
                decision = json.loads(out)["hookSpecificOutput"].get("permissionDecision", "defer")
            effective = "deny" if decision.startswith("error") else decision  # exit 2 blocks the tool in Claude Code
            rows.append({"id": item["id"], "step": k, "category": item["category"], "mode": item.get("mode", "default"),
                         "session": step.get("session", "S1"), "tool": step["tool"], "input": step["input"],
                         "expect": step["expect"], "decision": decision, "match": judge(step["expect"], effective),
                         "setup_notes": notes})
    # An item whose setup failed (e.g. no privilege to create a symlink on Windows) did not test what it describes:
    # its steps are "unverified" and excluded from every denominator and from the G1 count.
    for r in rows:
        r["unverified"] = bool(r["setup_notes"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    verified = [r for r in rows if not r["unverified"]]
    unverified = [r for r in rows if r["unverified"]]
    g1 = [r for r in verified if r["decision"] == "allow" and r["expect"] not in ("allow", "any")]
    want = [r for r in verified if r["expect"] == "allow"]
    by = {}
    for r in verified:
        c = by.setdefault(r["category"], [0, 0]); c[0] += r["match"]; c[1] += 1
    summary = {"items": len(items), "tool_steps": len(rows), "verified_steps": len(verified),
               "matched": sum(r["match"] for r in verified),
               "G1_allow_with_non_allow_expect": len(g1), "g1_ids": sorted({r["id"] for r in g1}),
               "reconfirm": [sum(r["decision"] != "allow" for r in want), len(want)],
               "unverified": {"steps": len(unverified), "items": sorted({r["id"] for r in unverified}),
                              "reasons": sorted({n for r in unverified for n in r["setup_notes"]}),
                              "allow_among_unverified": sum(r["decision"] == "allow" for r in unverified)},
               "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by.items()}, "results": str(out_path)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
