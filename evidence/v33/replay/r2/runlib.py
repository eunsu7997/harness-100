import json, os, subprocess, tempfile, shutil, uuid

import os
PKG = os.environ["H100_PKG"]
HOOK = PKG + r"\hooks\claude_code_hook.py"
WORK = r"<SCRATCH>\r2work"
OUTDIR = os.environ["H100_REPLAY_OUT"]


def call(payload, state, raw=False):
    env = dict(os.environ)
    env["HARNESS100_HOOK_STATE"] = state
    data = payload if raw else json.dumps(payload, ensure_ascii=False)
    p = subprocess.run(["python", "-I", "-B", HOOK], input=data.encode("utf-8"),
                       capture_output=True, env=env, timeout=35)
    out = p.stdout.decode("utf-8", "replace").strip()
    dec = "defer"
    reason = ""
    if out:
        try:
            j = json.loads(out)
            h = j.get("hookSpecificOutput", {})
            dec = h.get("permissionDecision", "?")
            reason = h.get("permissionDecisionReason", "")
        except Exception:
            dec = "unparsed"
            reason = out[:200]
    return dec, p.returncode, reason, p.stderr.decode("utf-8", "replace")[:200]


def subst(o, P, OUT):
    if isinstance(o, str):
        return o.replace("{P}", P).replace("{OUT}", OUT)
    if isinstance(o, list):
        return [subst(x, P, OUT) for x in o]
    if isinstance(o, dict):
        return {k: subst(v, P, OUT) for k, v in o.items()}
    return o


def run_item(item, base):
    d = tempfile.mkdtemp(dir=base)
    P = os.path.join(d, "proj")
    OUT = os.path.join(d, "outside")
    state = os.path.join(d, "state")
    for x in (P, OUT, state):
        os.makedirs(x, exist_ok=True)
    sid = "s" + uuid.uuid4().hex[:8]
    mode = item.get("mode", "default")
    turn_res = []
    for t in item.get("turns", []):
        cwd = P
        if isinstance(t, dict):
            cwd = subst(t.get("cwd", "{P}"), P, OUT)
            t = t["text"]
        r = call({"hook_event_name": "UserPromptSubmit", "session_id": sid,
                  "prompt": subst(t, P, OUT), "cwd": cwd}, state)
        turn_res.append(r[:2])
    res = []
    for pr in item["probes"]:
        pl = {"hook_event_name": "PreToolUse", "session_id": sid,
              "tool_name": pr["tool"], "tool_input": subst(pr["input"], P, OUT),
              "permission_mode": pr.get("mode", mode), "cwd": subst(pr.get("cwd", "{P}"), P, OUT)}
        dec, rc, reason, err = call(pl, state)
        res.append({"decision": dec, "rc": rc, "reason": reason[:160], "err": err})
    return res, turn_res, d
