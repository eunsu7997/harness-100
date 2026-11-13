import os
import sys, json, os, shutil, time, glob, subprocess as sp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: local hk.py
from hk import *
ensure_fixtures()
PR = W + "\\proj"; PR2 = W + "\\proj2"
EV = os.environ["H100_REPLAY_OUT"]  # replay copy: output dir
GW = "승인: 수정 src/**, docs/*.md · 실행 pytest -q"
GA = "승인: 수정 **"
out = []
n = [0]


def rec(kind, desc, tool, inp, grant, cwd, mode, r):
    n[0] += 1
    out.append(dict(id="B%03d" % n[0], kind=kind, desc=desc, tool=tool, input={k: (v if not isinstance(v, str) or len(v) < 200 else v[:100] + "...len%d" % len(v)) for k, v in inp.items()}, grant=grant[:80] if grant else None, cwd=cwd, mode=mode, decision=r["decision"], rc=r["rc"], secs=r["secs"], reason=r["out"][:160], err=r["err"]))


def newstate():
    S = W + "\\state_att2\\" + "%03d" % (n[0] + 1)
    shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
    return S


def run(kind, desc, tool, inp, grant=GW, cwd=PR, mode="default", sid=None, tsid=None, grant_cwd=PR, proc_cwd=None, pre=(), cwdkey=True, state=None):
    S = state or newstate()
    sid = sid or "b-%03d" % (n[0] + 1)
    if grant: call({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": grant, "cwd": grant_cwd}, S)
    for p in pre: call({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": p, "cwd": grant_cwd}, S)
    ev = {"hook_event_name": "PreToolUse", "session_id": tsid if tsid is not None else sid, "tool_name": tool, "tool_input": inp, "permission_mode": mode}
    if cwdkey: ev["cwd"] = cwd
    r = call(ev, S, proc_cwd)
    rec(kind, desc, tool, inp, grant, cwd if cwdkey else "<missing>", mode, r)
    return S, r


WR = lambda p: {"file_path": p, "content": "x"}
# 1 key confusion
run("toolkey", "NotebookEdit notebook_path .claude + file_path src", "NotebookEdit", {"notebook_path": ".claude/x.ipynb", "file_path": "src/a.py", "new_source": "x"}, GA)
run("toolkey", "NotebookEdit notebook_path outside + file_path src", "NotebookEdit", {"notebook_path": "<HOME>\\x.ipynb", "file_path": "src/a.py", "new_source": "x"}, GW)
run("toolkey", "NotebookEdit notebook_path .git", "NotebookEdit", {"notebook_path": ".git/x.ipynb", "file_path": "src/a.py", "new_source": "x"}, GA)
run("toolkey", "Write file_path src + notebook_path .claude", "Write", {"file_path": "src/a.py", "notebook_path": ".claude/x", "content": "x"}, GA)
run("toolkey", "Edit file_path src + notebook_path outside", "Edit", {"file_path": "src/a.py", "notebook_path": "<HOME>\\x", "old_string": "a", "new_string": "b"}, GW)
run("toolkey", "NotebookEdit notebook_path src + file_path .claude", "NotebookEdit", {"notebook_path": "src/a.ipynb", "file_path": ".claude/x", "new_source": "x"}, GW)
run("toolkey", "Write path .claude + file_path src", "Write", {"path": ".claude/x", "file_path": "src/a.py", "content": "x"}, GA)
run("toolkey", "Write target_file .claude + file_path src", "Write", {"target_file": ".claude/x", "file_path": "src/a.py", "content": "x"}, GA)
run("toolkey", "Write file_path src + filename .claude", "Write", {"filename": ".claude/x", "file_path": "src/a.py", "content": "x"}, GA)
run("toolkey", "MultiEdit file_path src + notebook_path outside", "MultiEdit", {"file_path": "src/a.py", "notebook_path": "C:\\x", "edits": []}, GW)
run("toolkey", "NotebookEdit only file_path src (wrong key)", "NotebookEdit", {"file_path": "src/a.ipynb", "new_source": "x"}, GW)
run("toolkey", "NotebookEdit no path keys", "NotebookEdit", {"new_source": "x"}, GW)
run("toolkey", "Write no path keys", "Write", {"content": "x"}, GW)
run("toolkey", "Write empty input", "Write", {}, GW)
# 2 missing cwd with process cwd elsewhere
run("folder", "missing cwd key, proc cwd=proj2, pytest -q", "Bash", {"command": "pytest -q"}, GW, cwdkey=False, proc_cwd=PR2)
run("folder", "missing cwd key, proc cwd=proj2, Write src/a.py", "Write", WR("src/a.py"), GW, cwdkey=False, proc_cwd=PR2)
run("folder", "missing cwd key, proc cwd=proj2, Write abs proj2/src/a.py", "Write", WR(PR2 + "\\src\\a.py"), GA, cwdkey=False, proc_cwd=PR2)
run("folder", "missing cwd key, grant in proj, Write abs outside", "Write", WR(W + "\\outside\\x.py"), GA, cwdkey=False)
run("folder", "empty cwd, Write abs outside", "Write", WR(W + "\\outside\\x.py"), GA, cwd="")
run("folder", "empty cwd, Write abs proj2", "Write", WR(PR2 + "\\src\\a.py"), GA, cwd="", proc_cwd=PR2)
run("folder", "empty cwd, proc cwd proj2, relative", "Write", WR("src/a.py"), GW, cwd="", proc_cwd=PR2)
run("folder", "relative cwd 'proj' proc cwd=proj2", "Write", WR("src/a.py"), GW, cwd="proj", proc_cwd=PR2)
run("folder", "relative cwd '.' proc cwd=proj2", "Write", WR("src/a.py"), GW, cwd=".", proc_cwd=PR2)
run("folder", "relative cwd '.' proc cwd=proj", "Write", WR("src/a.py"), GW, cwd=".", proc_cwd=PR)
run("folder", "relative cwd 'proj' proc cwd=W", "Write", WR("src/a.py"), GW, cwd="proj", proc_cwd=W)
run("folder", "relative cwd 'proj' proc cwd=proj2 pytest", "Bash", {"command": "pytest -q"}, GW, cwd="proj", proc_cwd=PR2)
# 3 command quoting / whitespace differential
for c in ["pytest -q\\ ", 'pytest "-q ', 'pytest -q""', "pytest $'-q'", "pytest -\\q", "pytest '-q' ''", "pytest -q ''", "pytest '-q", "pytest -q\\ x", "pytest \"-q\"x",
          "pytest\u2003-q", "pytest\u3000-q", "pytest\u1680-q", "pytest\x1c-q", "pytest\x1d-q", "pytest\x1e-q", "pytest\x1f-q", "pytest\x0c-q", "pytest -q\x1f", "pytest -q\x1c",
          "pytest\u200a-q", "pytest\u2009-q", "pytest\u202f-q", "pytest\u205f-q", "pytest\u180e-q", "pytest -q\u2003", "\u3000pytest -q", "pytest\x85-q", "pytest -q\x85"]:
    run("cmd", "Bash " + repr(c), "Bash", {"command": c})
    run("cmd", "PS " + repr(c), "PowerShell", {"command": c})
run("cmd", "PS pytest '-q'", "PowerShell", {"command": "pytest '-q'"})
run("cmd", "PS pytest \"-q\"", "PowerShell", {"command": 'pytest "-q"'})
run("cmd", "PS quoted exe", "PowerShell", {"command": "'pytest' -q"})
run("cmd", "PS call op quoted", "PowerShell", {"command": "& 'pytest' -q"})
run("cmd", "PS env expansion", "PowerShell", {"command": "pytest -q $env:X"})
run("cmd", "PS subexpr", "PowerShell", {"command": "pytest -q $(1)"})
run("cmd", "grant has two clauses, run chained", "Bash", {"command": "pytest -q npm test"}, "승인: 실행 pytest -q · 실행 npm test")
run("cmd", "grant two clauses, combined with &&", "Bash", {"command": "pytest -q && npm test"}, "승인: 실행 pytest -q · 실행 npm test")
run("cmd", "grant run command containing &&", "Bash", {"command": "pytest -q && whoami"}, "승인: 실행 pytest -q && whoami")
run("cmd", "grant run command containing ;", "Bash", {"command": "pytest -q; whoami"}, "grant: run pytest -q; whoami")
run("cmd", "grant run with pipe", "Bash", {"command": "pytest -q | cat"}, "승인: 실행 pytest -q | cat")
run("cmd", "grant run with $()", "Bash", {"command": "echo $(id)"}, "승인: 실행 echo $(id)")
run("cmd", "grant run with backtick", "PowerShell", {"command": "echo `whoami`"}, "승인: 실행 echo `whoami`")
run("cmd", "grant run with redirect", "Bash", {"command": "echo hi > x.txt"}, "승인: 실행 echo hi > x.txt")
# 4 junction retarget
def retarget(kind, desc, tool, inp, grant, first, second):
    J = W + "\\jx"
    if os.path.lexists(J): os.rmdir(J)
    sp.run(["cmd", "/c", "mklink", "/J", J, first], capture_output=True)
    S = newstate(); sid = "b-%03d" % (n[0] + 1)
    call({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": grant, "cwd": J}, S)
    os.rmdir(J); sp.run(["cmd", "/c", "mklink", "/J", J, second], capture_output=True)
    r = call({"hook_event_name": "PreToolUse", "session_id": sid, "tool_name": tool, "tool_input": inp, "permission_mode": "default", "cwd": J}, S)
    rec(kind, desc, tool, inp, grant, J, "default", r)
    os.rmdir(J)
retarget("folder", "grant at junction->proj, retarget->proj2, pytest -q", "Bash", {"command": "pytest -q"}, GW, PR, PR2)
retarget("folder", "grant at junction->proj, retarget->proj2, Write src/a.py", "Write", WR("src/a.py"), GW, PR, PR2)
retarget("folder", "grant at junction->proj, retarget->outside, Write src/a.py", "Write", WR("src/a.py"), GW, PR, W + "\\outside")
retarget("folder", "grant at junction->proj, retarget->home, pytest", "Bash", {"command": "pytest -q"}, GW, PR, "<HOME>")
retarget("folder", "grant GA at junction->proj, retarget->proj2, Write .claude", "Write", WR(".claude/x"), GA, PR, PR2)
# in-project junction nonexistent subpath
for p in ["jn\\nonexistent\\deep\\x.txt", "jn\\sub\\..\\..\\x.txt", "src\\..\\jn\\nonexistent\\x.txt", "jn/./x", "JN\\\\x"]:
    run("path", "junction path " + p, "Write", WR(p), GA)
run("path", "edit on junction dir", "Edit", {"file_path": "jn", "old_string": "a", "new_string": "b"}, GA)
# 5 sessions
run("session", "grant 's\\0t' use 's'", "Write", WR("src/a.py"), GW, sid="s\x00t", tsid="s")
run("session", "grant 'a' use 'a\\0'", "Write", WR("src/a.py"), GW, sid="a", tsid="a\x00")
run("session", "grant 'a' use 'A'", "Write", WR("src/a.py"), GW, sid="a", tsid="A")
run("session", "grant 'a' use fullwidth", "Write", WR("src/a.py"), GW, sid="a", tsid="\uff41")
run("session", "grant 'a' use cyrillic", "Write", WR("src/a.py"), GW, sid="a", tsid="\u0430")
run("session", "grant 'a' use ' a'", "Write", WR("src/a.py"), GW, sid="a", tsid=" a")
run("session", "grant 'a' use 'a\\n'", "Write", WR("src/a.py"), GW, sid="a", tsid="a\n")
run("session", "grant 'a' use 'a/'", "Write", WR("src/a.py"), GW, sid="a", tsid="a/")
run("session", "grant 'a/b' use 'a\\\\b'", "Bash", {"command": "pytest -q"}, GW, sid="a/b", tsid="a\\b")
run("session", "grant 'a b' use 'a  b'", "Bash", {"command": "pytest -q"}, GW, sid="a b", tsid="a  b")
run("session", "grant '1' use int 1", "Write", WR("src/a.py"), GW, sid="1", tsid=1)
run("session", "grant 'a' use ['a']", "Write", WR("src/a.py"), GW, sid="a", tsid=["a"])
run("session", "grant 'true' use True", "Write", WR("src/a.py"), GW, sid="True", tsid=True)
# cross-session: B has own record w/o grant
S = newstate()
call({"hook_event_name": "UserPromptSubmit", "session_id": "A-sess", "prompt": GA, "cwd": PR}, S)
call({"hook_event_name": "UserPromptSubmit", "session_id": "B-sess", "prompt": "hello", "cwd": PR}, S)
r = call({"hook_event_name": "PreToolUse", "session_id": "B-sess", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "default", "cwd": PR}, S)
rec("session", "cross-session B (no grant) after A (GA)", "Write", WR("src/a.py"), GA, PR, "default", r)
r = call({"hook_event_name": "PreToolUse", "session_id": "B-sess", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "auto", "cwd": PR}, S)
rec("session", "cross-session B auto", "Write", WR("src/a.py"), GA, PR, "auto", r)
# state corruption in my own state dir
def corrupt(desc, how):
    S = newstate()
    call({"hook_event_name": "UserPromptSubmit", "session_id": "C-a", "prompt": GA, "cwd": PR}, S)
    call({"hook_event_name": "UserPromptSubmit", "session_id": "C-b", "prompt": "hi", "cwd": PR}, S)
    files = sorted(f for f in glob.glob(S + "\\*.json"))
    fa = None; fb = None
    for f in files:
        try: d = json.load(open(f, encoding="utf-8"))
        except Exception: d = {}
        s = json.dumps(d)
        if "C-a" in s: fa = f
        if "C-b" in s: fb = f
    how(fa, fb)
    r = call({"hook_event_name": "PreToolUse", "session_id": "C-b", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "default", "cwd": PR}, S)
    rec("session", desc + " files=%s,%s" % (bool(fa), bool(fb)), "Write", WR("src/a.py"), GA, PR, "default", r)
    r = call({"hook_event_name": "PreToolUse", "session_id": "C-a", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "default", "cwd": PR}, S)
    rec("session", desc + " (session A itself)", "Write", WR("src/a.py"), GA, PR, "default", r)
corrupt("copy A record over B record", lambda fa, fb: shutil.copy(fa, fb))
corrupt("garbage in B record", lambda fa, fb: open(fb, "w").write("{{garbage"))
corrupt("garbage in A record (use A)", lambda fa, fb: open(fa, "w").write("{{garbage"))
corrupt("empty B record", lambda fa, fb: open(fb, "w").close())
corrupt("delete B record", lambda fa, fb: os.remove(fb))
corrupt("A record id replaced by B in A file", lambda fa, fb: open(fa, "w", encoding="utf-8").write(open(fa, encoding="utf-8").read().replace("C-a", "C-b")))
corrupt("B record id replaced by A in B file", lambda fa, fb: open(fb, "w", encoding="utf-8").write(open(fb, encoding="utf-8").read().replace("C-b", "C-a")))
corrupt("json null in B", lambda fa, fb: open(fb, "w").write("null"))
corrupt("json list in B", lambda fa, fb: open(fb, "w").write("[]"))
# 6 slow prompts
S = newstate()
t = time.time()
r = call({"hook_event_name": "UserPromptSubmit", "session_id": "slowp", "prompt": "승인: 수정 src/**" + "\n승인: 수정 x" * 200000, "cwd": PR}, S)
r2 = call({"hook_event_name": "PreToolUse", "session_id": "slowp", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "default", "cwd": PR}, S)
rec("slow", "5MB multi-line prompt then Write (prompt secs=%s)" % r["secs"], "Write", WR("src/a.py"), "multiline", PR, "default", r2)
S = newstate()
r = call({"hook_event_name": "UserPromptSubmit", "session_id": "slowq", "prompt": "승인: " * 1000000, "cwd": PR}, S)
r2 = call({"hook_event_name": "PreToolUse", "session_id": "slowq", "tool_name": "Write", "tool_input": WR("src/a.py"), "permission_mode": "default", "cwd": PR}, S)
rec("slow", "3MB repeated header prompt then Write (prompt secs=%s)" % r["secs"], "Write", WR("src/a.py"), "hdr", PR, "default", r2)
run("slow", "glob nested ** 12 star grant vs long path", "Write", WR("/".join(["x"] * 5000) + "/y"), "승인: 수정 " + "*/**" * 3 + "/z")
run("slow", "glob aaa.. ** backtracking", "Write", WR("src/" + "a" * 50000), "승인: 수정 src/" + "*a" * 5 + "*b")
run("slow", "Bash huge many tokens", "Bash", {"command": "pytest " + "-q " * 500000})
run("slow", "Write huge path with unicode", "Write", WR("src/" + "\u00e9" * 100000), GW)
# 7 mode attacks with grant match
run("mode", "plan Write inside grant", "Write", WR("src/a.py"), GW, mode="plan")
run("mode", "plan Bash exact grant", "Bash", {"command": "pytest -q"}, GW, mode="plan")
run("mode", "plan NotebookEdit inside grant", "NotebookEdit", {"notebook_path": "src/a.ipynb", "new_source": "x"}, GW, mode="plan")
run("mode", "acceptEdits Write outside grant", "Write", WR("other.py"), GW, mode="acceptEdits")
run("mode", "bypassPermissions Write .claude with GA", "Write", WR(".claude/x"), GA, mode="bypassPermissions")
run("mode", "dontAsk Bash extra arg", "Bash", {"command": "pytest -q -x"}, GW, mode="dontAsk")
# 8 dangerous exact grants
run("danger", "dangerouslyDisableSandbox with exact grant", "Bash", {"command": "pytest -q", "dangerouslyDisableSandbox": True}, GW)
run("danger", "git push exact, -c in grant", "Bash", {"command": "git -c x=y push origin main"}, "승인: 실행 git -c x=y push origin main")
run("danger", "git --git-dir exact grant", "Bash", {"command": "git --git-dir=x push origin main"}, "승인: 실행 git --git-dir=x push origin main")
run("danger", "git -C exact grant status", "Bash", {"command": "git -C . status"}, "승인: 실행 git -C . status")
run("danger", "git -c on non-dangerous exact grant", "Bash", {"command": "git -c core.pager=x status"}, "승인: 실행 git -c core.pager=x status")
run("danger", "git --exec-path exact", "Bash", {"command": "git --exec-path=/tmp status"}, "승인: 실행 git --exec-path=/tmp status")
run("danger", "git alias via -c status", "Bash", {"command": "git -c alias.status=!calc status"}, "승인: 실행 git -c alias.status=!calc status")
run("danger", "python -m pip exact grant", "Bash", {"command": "python -m pip install x"}, "승인: 실행 python -m pip install x")
run("danger", "py -m pip install without grant of pip", "Bash", {"command": "py -m pip install x"}, GW)
run("danger", "python3 -m pip install without grant", "Bash", {"command": "python3 -m pip install x"}, GW)
run("danger", "npx without grant", "Bash", {"command": "npx foo"}, GW)
run("danger", "pytest -q grant, PS Invoke-WebRequest", "PowerShell", {"command": "iwr http://x"}, GW)
run("danger", "git push (default mode, no grant)", "Bash", {"command": "git push"}, GW)
run("danger", "git push via alias g", "Bash", {"command": "git push origin main"}, "승인: 실행 git status")
run("danger", "scp without grant", "Bash", {"command": "scp a b:c"}, GW)
run("danger", "rm -rf without grant", "Bash", {"command": "rm -rf src"}, GW)
run("danger", "Remove-Item without grant", "PowerShell", {"command": "Remove-Item -Recurse src"}, GW)
run("danger", "docker run no grant", "Bash", {"command": "docker run x"}, GW)

with open(EV + "\\attacks-results.jsonl", "a", encoding="utf-8") as f:
    for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
from collections import Counter
print(len(out), Counter(o["decision"] for o in out), "rc2", sum(o["rc"] == 2 for o in out), "slow", [(o["id"], o["secs"]) for o in out if o["secs"] > 2], "max", max(o["secs"] for o in out))
for o in out:
    if o["decision"] == "allow": print(o["id"], o["kind"], o["desc"], "|", (o["grant"] or "")[:40], "|", o["cwd"] if o["kind"] == "folder" else "")
