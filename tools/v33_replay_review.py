"""v3.3 replay of an independent reviewer's step sets (set K / attack cases) against the current hook.

Same payloads as the reviewer's hooklib.py (fresh state folder per item, `omit` and `event` honoured).
Usage: python -I -B -X utf8 tools/v33_replay_review.py <cases.jsonl> <out.jsonl> [<judged_allows.json>]
With judged_allows.json, every allow is classified: covered in the reviewer's judgement / NOT covered / new (needs
judging). Hold-out files are only read.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PKG, "hooks", "claude_code_hook.py")


def call(state, payload):
    env = dict(os.environ)
    env["HARNESS100_HOOK_STATE"] = state
    t = time.time()
    p = subprocess.run([sys.executable, "-I", "-B", HOOK], input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, env=env, timeout=60)
    out = p.stdout.decode("utf-8", "replace").strip()
    dec = "defer"
    if out:
        try:
            ho = json.loads(out)["hookSpecificOutput"]
            dec = ho.get("permissionDecision") or ("ctx" if "additionalContext" in ho else "??")
        except Exception:
            dec = "??"
    if p.returncode == 2 and dec == "defer":
        dec = "deny"
    return dec, p.returncode, round(time.time() - t, 3), out


def ok(exp, dec):
    return {"allow": dec == "allow", "defer": dec == "defer", "deny": dec == "deny", "not_allow": dec != "allow",
            "not_deny": dec != "deny", "any": True}[exp]


def main():
    cases, out_path = sys.argv[1], sys.argv[2]
    judged = {}
    if len(sys.argv) > 3:
        for row in json.load(open(sys.argv[3], encoding="utf-8")):
            judged[(row["id"], row["step"])] = row["covered"]
    work = tempfile.mkdtemp(prefix="v33rr_")
    rows, slow = [], 0.0
    for line in open(cases, encoding="utf-8").read().split("\n"):
        if not line.strip():
            continue
        item = json.loads(line)
        state = tempfile.mkdtemp(prefix="st_", dir=work)
        matched = True
        for index, step in enumerate(item["steps"]):
            if isinstance(step, list):  # round-1 reviewer list form: [type, session, cwd, text|tool, input, mode] / [raw, payload]
                if step[0] == "raw":
                    step = {"type": "raw", "payload": step[1]}
                elif step[0] == "prompt":
                    step = {"type": "prompt", "session": step[1], "cwd": step[2], "text": step[3]}
                else:
                    step = {"type": "tool", "session": step[1], "cwd": step[2], "tool": step[3], "input": step[4],
                            "mode": step[5]}
            if step["type"] == "raw":
                payload = step["payload"]
                dec, rc, secs, out = call(state, payload)
                slow = max(slow, secs)
                rows.append({"id": item["id"], "step": index, "category": item.get("category", item.get("tech")),
                             "tool": payload.get("tool_name") if isinstance(payload, dict) else None,
                             "input": payload.get("tool_input") if isinstance(payload, dict) else None,
                             "mode": payload.get("permission_mode", "(absent)") if isinstance(payload, dict) else None,
                             "decision": dec, "rc": rc, "secs": secs, "reason": out[:300]})
                continue
            step = dict(step)
            step.setdefault("mode", item.get("mode", "default"))  # set L: mode on the item
            if step["type"] == "prompt":
                payload = {"hook_event_name": "UserPromptSubmit", "session_id": step["session"], "prompt": step["text"],
                           "cwd": step["cwd"]}
                call(state, payload)
                continue
            payload = {"hook_event_name": step.get("event", "PreToolUse"), "session_id": step["session"],
                       "tool_name": step["tool"], "tool_input": step["input"],
                       "permission_mode": step.get("mode", "default"), "cwd": step["cwd"]}
            for key in step.get("omit", []):
                payload.pop(key, None)
            dec, rc, secs, out = call(state, payload)
            slow = max(slow, secs)
            row = {"id": item["id"], "step": index, "category": item.get("category"), "tool": step["tool"],
                   "input": step["input"], "mode": step.get("mode", "default"), "decision": dec, "rc": rc, "secs": secs,
                   "reason": out[:300]}
            if "expect" in step:
                row["expect"] = step["expect"]
                row["match"] = ok(step["expect"], dec)
                matched &= row["match"]
            if dec == "allow" and judged is not None and len(sys.argv) > 3:
                prior = judged.get((item["id"], index))
                row["judgement_round0"] = ("covered" if prior else "NOT covered") if prior is not None else "new allow"
            rows.append(row)
        shutil.rmtree(state, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    allows = [r for r in rows if r["decision"] == "allow"]
    summary = {"cases": cases, "tool_steps": len(rows), "allows": len(allows),
               "expect_steps": sum(1 for r in rows if "expect" in r),
               "matched": sum(1 for r in rows if r.get("match")),
               "allow_against_expect": [r["id"] for r in rows if r["decision"] == "allow" and "expect" in r
                                        and r["expect"] not in ("allow", "any", "not_deny")],
               "exit2": sum(1 for r in rows if r["rc"] == 2), "slowest_s": slow}
    if len(sys.argv) > 3:
        summary["allow_judgement"] = {k: [r["id"] for r in allows if r.get("judgement_round0") == k]
                                      for k in ("covered", "NOT covered", "new allow")}
        summary["allow_judgement_counts"] = {k: len(v) for k, v in summary["allow_judgement"].items()}
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
