import json, sys, os, subprocess, tempfile, shutil, uuid
import os
PKG = os.environ["H100_PKG"]
HOOK = PKG + r"\hooks\claude_code_hook.py"
inp, outp = sys.argv[1], sys.argv[2]
BASE = tempfile.mkdtemp(prefix="rv_", dir=r"<SCRATCH>")

def sub(o, ctx):
    if isinstance(o, str):
        for k, v in ctx.items():
            o = o.replace("{" + k + "}", v)
        return o
    if isinstance(o, list): return [sub(x, ctx) for x in o]
    if isinstance(o, dict): return {k: sub(v, ctx) for k, v in o.items()}
    return o

def call(payload, state, cwd, raw=None):
    env = dict(os.environ); env["HARNESS100_HOOK_STATE"] = state
    data = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8", "surrogatepass")
    if isinstance(data, str): data = data.encode("utf-8")
    try:
        p = subprocess.run(["python", "-I", "-B", HOOK], input=data, capture_output=True, env=env, cwd=cwd, timeout=60)
    except subprocess.TimeoutExpired:
        return "timeout", -1, "", "timeout>60s"
    out = p.stdout.decode("utf-8", "replace").strip()
    dec = "defer"
    if p.returncode == 2: dec = "error_rc2"
    elif p.returncode != 0: dec = f"error_rc{p.returncode}"
    elif out:
        try:
            dec = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            dec = "unparsed"
    return dec, p.returncode, out[:400], p.stderr.decode("utf-8", "replace")[:300]

def match(exp, dec):
    if exp == "any": return True
    if exp == "not_allow": return dec != "allow"
    if exp == "not_deny": return dec != "deny" and dec != "error_rc2"
    if exp == "deny": return dec in ("deny", "error_rc2")
    return dec == exp

res = open(outp, "w", encoding="utf-8")
for line in open(inp, encoding="utf-8"):
    it = json.loads(line)
    d = os.path.join(BASE, it["id"]); proj = os.path.join(d, "proj"); state = os.path.join(d, "state")
    out_dir = os.path.join(d, "outside"); os.makedirs(proj); os.makedirs(state); os.makedirs(out_dir)
    ctx = {"CWD": proj, "STATE": state, "OUT": out_dir}
    for s in it.get("setup", []):
        if "mkdir" in s: os.makedirs(os.path.join(proj, s["mkdir"]), exist_ok=True)
        if "junction" in s:
            link = os.path.join(proj, s["junction"]); os.makedirs(os.path.dirname(link), exist_ok=True)
            subprocess.run(["cmd", "/c", "mklink", "/J", link, out_dir], capture_output=True)
    for s_ in it.get("setup", []):
        if "state_file" in s_:
            c_ = sub(s_["content"], ctx)
            open(os.path.join(state, s_["state_file"]), "w", encoding="utf-8", errors="surrogatepass").write(c_ if isinstance(c_, str) else json.dumps(c_))
    sid = "s-" + uuid.uuid4().hex[:8]
    mode = it.get("mode")
    for t in it["turns"]:
        if isinstance(t, str): t = {"text": t}
        t = sub(t, ctx)
        s = t.get("sid", sid); cwd = t.get("cwd", proj)
        pl = {"hook_event_name": "UserPromptSubmit", "session_id": s, "prompt": t["text"], "cwd": cwd}
        if mode: pl["permission_mode"] = mode
        call(pl, state, proj)
    for pr in it["probes"]:
        pr = sub(pr, ctx)
        s = pr.get("sid", sid); cwd = pr.get("cwd", proj)
        pm = pr.get("mode", mode)
        pl = {"hook_event_name": "PreToolUse", "session_id": s, "tool_name": pr["tool"], "tool_input": pr["input"], "cwd": cwd}
        if pm is not None and pm != "__omit__": pl["permission_mode"] = pm
        for k, v in pr.get("override", {}).items():
            if v == "__del__": pl.pop(k, None)
            else: pl[k] = v
        raw = pr["raw"].encode("utf-8") if "raw" in pr else None
        dec, rc, out, err = call(pl, state, proj, raw)
        r = {"id": it["id"], "category": it["category"], "mode": pm, "tool": pr["tool"], "input": pr["input"],
             "expect": pr["expect"], "decision": dec, "rc": rc, "matched": match(pr["expect"], dec), "stdout": out, "stderr": err}
        if "note" in pr: r["note"] = pr["note"]
        res.write(json.dumps(r, ensure_ascii=False) + "\n")
    if it.get("check_outside"):
        pass
res.close()
print("BASE", BASE)
