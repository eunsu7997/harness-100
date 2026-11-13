import json, os, subprocess, sys, time, shutil, ctypes

PKG = r"<PROJECT_ROOT>\harness-100-v3.2-cc"
HOOK = PKG + r"\hooks\claude_code_hook.py"
OUT = PKG + r"\evidence\v32\review"
RV = r"<SCRATCH>\rv"


# ---------- builders ----------
def prompt(text, s=None, cwd="{P}"):
    return {"type": "prompt", "session": s, "cwd": cwd, "text": text}


def tool(name, inp, expect, s=None, cwd="{P}", mode=None):
    d = {"type": "tool", "session": s, "cwd": cwd, "tool": name, "input": inp, "expect": expect}
    if mode:
        d["mode"] = mode
    return d


def state(op, s, frm=None):
    return {"type": "state", "op": op, "session": s, "from": frm}


def W(path, content="x"):
    return ("Write", {"file_path": path, "content": content})


def finalize(prefix, cat, items):
    out = []
    for i, it in enumerate(items, 1):
        iid = "%s%02d" % (prefix, i)
        sid = "sH-" + iid
        steps = []
        for st in it["steps"]:
            st = dict(st)
            if st.get("session") is None:
                st["session"] = sid
            steps.append(st)
        out.append({"id": iid, "category": cat, "mode": it.get("mode", "default"),
                    "setup": it.get("setup", []), "steps": steps, "note": it.get("note", "")})
    return out


def gw(grant, path, expect, tname="Write", mode="default", note="", setup=None, cwd="{P}"):
    if tname == "Write":
        inp = {"file_path": path, "content": "x"}
    elif tname == "Edit":
        inp = {"file_path": path, "old_string": "a", "new_string": "b"}
    elif tname == "MultiEdit":
        inp = {"file_path": path, "edits": [{"old_string": "a", "new_string": "b"}]}
    else:
        inp = {"notebook_path": path, "new_source": "x"}
    return {"mode": mode, "note": note, "setup": setup or [],
            "steps": [prompt(grant, cwd=cwd), tool(tname, inp, expect, cwd=cwd)]}


def gc(grant, cmd, expect, tname="Bash", mode="default", note="", cwd="{P}", cwd2=None):
    return {"mode": mode, "note": note, "setup": [],
            "steps": [prompt(grant, cwd=cwd), tool(tname, {"command": cmd}, expect, cwd=cwd2 or cwd)]}


# ---------- runner ----------
def short83(p):
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024)
        return buf.value if n else p
    except Exception:
        return p


def snapshot(d):
    s = set()
    for r, ds, fs in os.walk(d):
        for f in fs:
            s.add(os.path.join(r, f))
    return s


def subst(o, m):
    if isinstance(o, str):
        for k, v in [(k, v) for k, v in m.items() if isinstance(v, str)]:
            o = o.replace(k, v)
        return o
    if isinstance(o, list):
        return [subst(x, m) for x in o]
    if isinstance(o, dict):
        return {k: subst(v, m) for k, v in o.items()}
    return o


def call_hook(obj, stdir, raw=None):
    env = dict(os.environ)
    env["HARNESS100_HOOK_STATE"] = stdir
    data = raw if raw is not None else json.dumps(obj).encode("utf-8")
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-I", "-B", HOOK], input=data, env=env,
                           capture_output=True, timeout=30)
        rc, so, se = p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        rc, so, se = -999, "", "TIMEOUT"
    dt = time.time() - t0
    dec = "defer"
    reason = ""
    if so.strip():
        try:
            j = json.loads(so)
            h = j.get("hookSpecificOutput", {})
            dec = h.get("permissionDecision", "?")
            reason = (h.get("permissionDecisionReason") or "")[:160]
        except Exception:
            dec = "unparsed"
            reason = so[:160]
    if rc == 2:
        dec = "deny"
    if rc == -999:
        dec = "TIMEOUT"
    return {"rc": rc, "decision": dec, "reason": reason, "secs": round(dt, 3), "stderr": se[:200]}


def ok(expect, dec, rc):
    if expect == "any":
        return True
    if expect == "allow":
        return dec == "allow"
    if expect == "defer":
        return dec == "defer"
    if expect == "deny":
        return dec == "deny"
    if expect == "not_allow":
        return dec != "allow"
    if expect == "not_deny":
        return dec != "deny"
    return False


def setup_item(it, m):
    P, P2 = m["{P}"], m["{P2}"]
    for d in (P + r"\src", P + r"\tests", P + r"\docs", P + r"\.claude", P + r"\.git\hooks",
              P + r"\longdirectoryname", P2 + r"\src"):
        os.makedirs(d, exist_ok=True)
    for op in it.get("setup", []):
        op = subst(op, m)
        k = op["op"]
        try:
            if k == "mkdir":
                os.makedirs(op["path"], exist_ok=True)
            elif k == "file":
                os.makedirs(os.path.dirname(op["path"]), exist_ok=True)
                open(op["path"], "w", encoding="utf-8").write(op.get("text", "x"))
            elif k == "junction":
                subprocess.run(["cmd", "/c", "mklink", "/J", op["path"], op["target"]], capture_output=True)
            elif k == "symlink":
                os.symlink(op["target"], op["path"], target_is_directory=True)
        except Exception as e:
            m.setdefault("_setup_err", []).append("%s:%s" % (k, e))


def run_set(items, path_out, work, stdir, runid):
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    if os.path.exists(stdir):
        shutil.rmtree(stdir, ignore_errors=True)
    os.makedirs(work); os.makedirs(stdir)
    sess_files = {}
    res = []
    for it in items:
        P = work + "\\p" + it["id"]
        P2 = work + "\\q" + it["id"]
        m = {"{P}": P, "{P2}": P2, "{W}": work, "{ST}": stdir, "{P83}": short83(P + r"\longdirectoryname"),
             "{PUP}": P.upper(), "{PFWD}": P.replace("\\","/"), "{HOOK}": HOOK, "{PKG}": PKG, "{HOME}": os.path.expanduser("~")}
        setup_item(it, m)
        for si, st0 in enumerate(it["steps"]):
            st = subst(st0, m)
            rec = {"id": it["id"], "category": it["category"], "step": si, "type": st["type"]}
            if st["type"] == "state":
                before = None
                files = sess_files.get(st["session"], [])
                note = "no-file"
                try:
                    if st["op"] == "truncate" and files:
                        open(files[0], "wb").close(); note = "truncated"
                    elif st["op"] == "garbage" and files:
                        open(files[0], "wb").write(b"\x00{not json[[\xff"); note = "garbage"
                    elif st["op"] == "delete" and files:
                        for f in files: os.remove(f)
                        note = "deleted"
                    elif st["op"] == "forge_from" and files:
                        src = sess_files.get(st["from"], [])
                        if src:
                            shutil.copyfile(src[0], files[0]); note = "forged-from-other"
                    elif st["op"] == "forge_rename" and sess_files.get(st["from"]):
                        # place other session's record file content under this session's name
                        pass
                except Exception as e:
                    note = "err:%s" % e
                rec.update({"op": st["op"], "note": note, "files": len(files)})
                res.append(rec); continue
            ev = {"hook_event_name": "UserPromptSubmit" if st["type"] == "prompt" else "PreToolUse",
                  "session_id": st["session"], "cwd": st["cwd"]}
            if st["type"] == "prompt":
                ev["prompt"] = st["text"]
            else:
                ev["tool_name"] = st["tool"]; ev["tool_input"] = st["input"]
                ev["permission_mode"] = st.get("mode") or it["mode"]
            if st.get("omit_session"):
                ev.pop("session_id")
            if st.get("nocwd"):
                ev.pop("cwd")
            if st.get("session_null"):
                ev["session_id"] = None
            before = snapshot(stdir)
            r = call_hook(ev, stdir)
            if st["type"] == "prompt":
                new = sorted(snapshot(stdir) - before)
                if new:
                    sess_files.setdefault(st["session"], []).extend(new)
            rec.update(r)
            if st["type"] == "tool":
                rec["tool"] = st["tool"]
                rec["input"] = st["input"]
                rec["expect"] = st["expect"]
                rec["mode"] = ev["permission_mode"]
                rec["match"] = ok(st["expect"], r["decision"], r["rc"])
            else:
                rec["text"] = st["text"][:100]
            res.append(rec)
    with open(path_out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return res
