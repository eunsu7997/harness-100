import os
import sys, json, os, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: local hk.py
from hk import *
ensure_fixtures()
PR = W + "\\proj"; PR2 = W + "\\proj2"; OUT = W + "\\outside"
EV = os.environ["H100_REPLAY_OUT"]  # replay copy: output dir
GW = "승인: 수정 src/**, docs/*.md · 실행 pytest -q"
GA = "승인: 수정 **"
A = []


def at(kind, desc, tool, inp, grant=GW, cwd=PR, mode="default", pre=None, sess=None):
    A.append(dict(kind=kind, desc=desc, tool=tool, input=inp, grant=grant, cwd=cwd, mode=mode, pre=pre or [], sess=sess))


def w(kind, path, grant=GA, tool="Write", **k):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    inp = {key: path}
    if tool == "Write": inp["content"] = "x"
    elif tool == "Edit": inp.update(old_string="a", new_string="b")
    elif tool == "MultiEdit": inp["edits"] = [{"old_string": "a", "new_string": "b"}]
    else: inp["new_source"] = "x"
    at(kind, "path:" + repr(path)[:80], tool, inp, grant, **k)


# --- Windows path forms, broad grant (GA) ---
for p in [".claude\\settings.json", ".claude/../.claude/x", "src\\..\\.claude\\x", ".claude.\\x", ".claude \\x", ".claude\\.\\x",
          ".claude\\\\x", ".git\\\\hooks\\\\x", ".Git/config", ".git::$DATA", ".claude::$INDEX_ALLOCATION\\x", ".claude:x",
          "src/a.py:Zone.Identifier", "src/a.py::$DATA", "CLAUDE~1/x", "%CD%\\.claude\\x", "%PROJ%\\src\\a.py", "$PWD/.claude/x",
          "${PWD}/.claude/x", "$env:USERPROFILE\\x", "~\\x", "~root/x", "~+/x", "C:.claude\\x", "D:x", "\\.claude\\x", "\\src\\a.py",
          "/src/a.py", "\\\\?\\" + PR + "\\.claude\\x", "\\\\?\\" + PR + "\\src\\a.py", "\\\\?\\UNC\\server\\share\\x", "\\\\.\\pipe\\x",
          "\\\\localhost\\C$<TMP>\\h100-v32-review2\\proj\\src\\a.py",
          "//localhost/C$<TMP>/h100-v32-review2/proj/src/a.py",
          "src\\CON", "src\\con.txt", "src\\PRN.py", "src\\AUX", "src\\COM1", "src\\LPT1.txt", "src\\NUL.py", "src\\CONIN$", "src\\CONOUT$",
          "src\\a.py.", "src\\a.py ", "src\\a.py...", "src\\ a.py", "src\\a<b.py", "src\\a>b.py", "src\\a|b.py", "src\\a?b.py", "src\\a*b.py",
          "src\\a\"b.py", "src\\a\u0000.py", "src\\a\x01.py", "src\\a\n.py", "src/" + "d/" * 150 + "f.py", "src/" + "d" * 5000 + ".py",
          "src/a/../../../outside.py", "src/../../outside/x.py", "src/..\\..\\x", PR + "\\src\\..\\..\\outside\\x", "jn\\x.txt", "src\\..\\jn\\x.txt", "jn",
          "jn\\sub\\x", PR + "\\jn\\x", "jn.\\x", "JN/x", "PROJ~1\\x", W + "\\PROJ~1\\src\\a.py", "SRC~1\\a.py",
          W + "\\state_setI2\\x", PKG + "\\hooks\\claude_code_hook.py", PKG + "\\hooks\\x.py", "<HOME>\\.claude\\settings.json",
          "\uff0eclaude/x", ".claude\u200b/x", ".claude\u00a0/x", "src\\a.py\u202e", ".\u0063laude/x", ".clAude\\X", ".GIT\\hooks\\pre-push",
          "src/../.git/x", "src/%2e%2e/.claude/x", "src/..%5c.claude/x", ".claude/", ".git/.", ".git/..", "..", ".", "", " ",
          "src/\\.claude/x", "src\\.\\.\\..\\.claude\\x", "a/.claude/x/../../../.claude/x", "\\\\.\\C:\\x", "C:\\", "<HOME>/x", "<HOME>\\x"]:
    w("path", p)
# grant-W glob-coverage attacks
for p in ["docs/sub/a.md", "docs/a.md.exe", "docs/.md", "src2/a.py", "srcx/a.py", "src", "a.py", "src/../a.py", "docs/a.MD", "docs\\\\a.md", "docs/a.md::$DATA", "docs/a.md:s", "SRC/A.PY", "Src\\a.py", "./src/a.py", "src//a.py", "src\\/a.py"]:
    w("glob", p, grant=GW)
# tool-name / key confusion
at("toolkey", "lowercase tool", "write", {"file_path": ".claude/x", "content": "x"}, GA)
at("toolkey", "tool trailing space", "Write ", {"file_path": ".claude/x", "content": "x"}, GA)
at("toolkey", "NotebookEdit file_path key", "NotebookEdit", {"file_path": ".claude/x.ipynb", "new_source": "x"}, GA)
at("toolkey", "Write path key", "Write", {"path": ".claude/x", "content": "x"}, GA)
at("toolkey", "Edit two keys", "Edit", {"file_path": "src/a.py", "filePath": ".claude/x", "old_string": "a", "new_string": "b"}, GA)
at("toolkey", "notebook+file keys", "NotebookEdit", {"file_path": "src/a.py", "notebook_path": ".claude/x.ipynb"}, GA)
at("toolkey", "file_path list", "Write", {"file_path": ["src/a.py", ".claude/x"], "content": "x"}, GA)
at("toolkey", "file_path number", "Write", {"file_path": 5, "content": "x"}, GA)
at("toolkey", "file_path null", "Write", {"file_path": None, "content": "x"}, GA)
at("toolkey", "file_path newline mix", "Write", {"file_path": "src/a.py\n.claude/x", "content": "x"}, GA)
at("toolkey", "MultiEdit edits with file_path", "MultiEdit", {"file_path": "src/a.py", "edits": [{"file_path": ".claude/x", "old_string": "a", "new_string": "b"}]}, GA)
at("toolkey", "mcp write tool", "mcp__fs__write_file", {"path": ".claude/x", "content": "x"}, GA)
at("toolkey", "mcp write outside", "mcp__fs__write_file", {"path": "<HOME>\\x", "content": "x"}, GA)
at("toolkey", "unknown tool Task", "Task", {"prompt": "write .claude/x"}, GA)
at("toolkey", "Bash with redirect to .claude", "Bash", {"command": "echo x > .claude/settings.json"}, GA)
at("toolkey", "PowerShell Set-Content .claude", "PowerShell", {"command": "Set-Content .claude/settings.json x"}, GA)
at("toolkey", "Bash tee outside", "Bash", {"command": "tee <HOME>/x.txt"}, GA)
# mode attacks
for m in ["bypassPermissions", "auto", "dontAsk", "plan", "acceptEdits", "AUTO", "weird", "", None]:
    at("mode", "Write .claude mode=%r" % m, "Write", {"file_path": ".claude/x", "content": "x"}, GA, mode=m)
    at("mode", "Write outside mode=%r" % m, "Write", {"file_path": "<HOME>\\x", "content": "x"}, GA, mode=m)
# command forms (grant GW: exact `pytest -q`)
cmds = ["pytest -q;x", "pytest -q&&x", "pytest -q||x", "pytest -q|x", "pytest -q\t", "pytest\t-q", "pytest -q#c", "pytest -q # c", "pytest -q\u2028x", "pytest -q\x00x",
        "pytest -q\x0bx", "pytest -q\x0cx", "pytest -q\u0085x", "pytest -q ^", "pytest -q %PATH%", "pytest -q $HOME", "pytest -q ${x}", "pytest -q ~", "pytest -q *",
        'pytest -q ""', "pytest -q ''", 'pytest "-q"', 'pytest -"q"', 'p"ytest" -q', "py\\test -q", "pytest -q\\", "pytest -q `", "pytest -q @(1)", "pytest -q @args",
        "pytest -q -", ". pytest -q", '& "pytest" -q', "pytest.exe -q", "pytest.EXE -q", "pytest -q.", "Pytest -q", "pytest -q:", "pytest -q\u00a0", "\ufeffpytest -q",
        "pytest -q\r", "\npytest -q", "pytest -q\n", "pytest -q\u200b", "\uff50ytest -q", "pytest \u2011q", "pytest \u2013q", "Invoke-Expression 'pytest -q'", "iex pytest -q",
        "pytest -q | Out-Null", "pytest -q 2>&1", "pytest -q 2>nul", "pytest -q >> x", "pytest -q < x", "pytest -q $(whoami)", "pytest -q `whoami`", "pytest -q\n\n", " \tpytest -q",
        "pytest -q" + " " * 5000, "pytest" + " " * 3000 + "-q", "pytest -q -- ", "pytest -q =", "(pytest -q)", "{pytest -q}", "pytest -q &", "pytest -q ;", "time pytest -q", "env pytest -q",
        "pytest -q\\\n", "pytest ^-q", "pytest -q 'a b'", "pytest   -q   ", "PYTEST -Q"]
for c in cmds:
    at("cmd", "Bash " + repr(c)[:60], "Bash", {"command": c})
    at("cmd", "PS " + repr(c)[:60], "PowerShell", {"command": c})
at("cmd", "extra key cwd", "Bash", {"command": "pytest -q", "cwd": "/"})
at("cmd", "extra key desc injection", "Bash", {"command": "pytest -q", "description": "x; rm -rf /"})
at("cmd", "run_in_background", "Bash", {"command": "pytest -q", "run_in_background": True})
at("cmd", "dangerouslyDisableSandbox", "Bash", {"command": "pytest -q", "dangerouslyDisableSandbox": True})
at("cmd", "timeout huge", "Bash", {"command": "pytest -q", "timeout": 10 ** 12})
at("cmd", "command list", "Bash", {"command": ["pytest", "-q"]})
at("cmd", "command none", "Bash", {"command": None})
at("cmd", "cmd key", "Bash", {"cmd": "pytest -q"})
at("cmd", "tool BashOutput", "BashOutput", {"command": "pytest -q;x"})
at("cmd", "Bash cwd-less tool tuple", "Bash", {"command": "cd / && pytest -q"})
at("cmd", "Bash cd then pytest", "Bash", {"command": "cd .. ; pytest -q"})
# danger grants
at("danger", "git push grant exact then -C", "Bash", {"command": "git -C . push origin main"}, "승인: 실행 git push origin main")
at("danger", "git push --git-dir", "Bash", {"command": "git --git-dir=x push origin main"}, "승인: 실행 git push origin main")
at("danger", "git -c grant exact", "Bash", {"command": "git -c a=b push origin main"}, "승인: 실행 git -c a=b push origin main")
at("danger", "git -C grant exact", "Bash", {"command": "git -C other push origin main"}, "승인: 실행 git -C other push origin main")
at("danger", "git push ext", "Bash", {"command": "git push origin main --force"}, "승인: 실행 git push origin main")
at("danger", "grant git then rm", "Bash", {"command": "git rm -rf ."}, "승인: 실행 git")
at("danger", "pip via python -m", "Bash", {"command": "python -m pip install x"}, "승인: 실행 python -m pip")
at("danger", "grant pip exact install", "Bash", {"command": "pip install x"}, "승인: 실행 pip install x")
at("danger", "rm grant exact", "PowerShell", {"command": "Remove-Item -Recurse x"}, "승인: 실행 Remove-Item -Recurse x")
at("danger", "curl without grant", "Bash", {"command": "curl http://x"}, GW)
at("danger", "npm install without grant", "Bash", {"command": "npm install"}, GW)
at("danger", "git commit without grant", "Bash", {"command": "git commit -m x"}, GW)
at("danger", "pytest wide grant 실행 pytest vs pytest -x", "Bash", {"command": "pytest -x"}, "승인: 실행 pytest")
# prompt-form attacks (grant string variants), then Write src/a.py under cwd PR
nfd = lambda s: __import__("unicodedata").normalize("NFD", s)
for g in [nfd("승인: 수정 src/**"), "승인: 수정 src/＊＊", "승인: 수정 src/**\u2028", "승인: 수정 src/**\r\n승인: 수정 docs/**", "\ufeff승인: 수정 src/**", "승인: 수정 src/**\x00",
          "승인: 수정 src/**\n", "승인: 수정 src/** 기간 세션", "승인: 수정 src/**·기간 작업", "승인: 수정 src/** · 기간 작업 ", "승인: 수정 src/** | 실행 x", "승인:수정 src/**", "승인 : 수정 src/**",
          "승인: 수정  src/**", "승인: 수정 src/** ;; ", "승인: 수정 src/**,", "승인: 수정 ,src/**", "승인: 수정 src/**, ../x", "승인: 수정 src/../../**", "승인: 수정 ./**", "승인: 수정 src\\**",
          "승인: 수정 {src,docs}/**", "승인: 수정 src/[a]*", "승인: 수정 src/**/../..", "grant: edit src/** ; run", "grant: edit src/**;run pytest -q", "grant: edit src/** / run pytest -q",
          "승인: 수정 *", "승인: 수정 **/*", "승인: 수정 .*/**", "승인: 수정 ?claude/**", "승인: 수정 ?git/**", "승인: 수정 .?lau*/**", "승인: 수정 .c*/**"]:
    at("grantform", "grant:" + repr(g)[:70], "Write", {"file_path": "src/a.py", "content": "x"}, g)
for g, p in [("승인: 수정 .?lau*/**", ".claude/x"), ("승인: 수정 .c*/**", ".claude/x"), ("승인: 수정 .*/**", ".git/hooks/x"), ("승인: 수정 ?git/**", ".git/x"),
             ("승인: 수정 **/x", ".claude/x"), ("승인: 수정 **/hooks/*", ".git/hooks/pre-commit"), ("승인: 수정 *", "a.py"), ("승인: 수정 **", "src/a.py")]:
    at("grantglob", "glob %s vs %s" % (g, p), "Write", {"file_path": p, "content": "x"}, g)
# folder / cwd tricks with GA
for cwd, path in [(PR + "\\.claude", "x"), (PR + "\\.git", "hooks\\x"), (PR + "\\src", "..\\.claude\\x"), (PR2, "x"), (W, "proj\\src\\a.py"), ("<HOME>", "x"),
                  (PR + "\\.CLAUDE", "x"), (PR + "\\jn", "x"), (OUT, "x"), (PR + "\\src\\..", "src\\a.py"), (PR + "\\..\\proj", "src\\a.py"), (".", "src\\a.py"), ("src", "a.py"),
                  (PR + "\\", ".claude\\x"), (PR + "\\.", ".claude\\x"), (PR2 + "\\back", ".claude\\x"), (W + "\\jproj", ".claude\\x"), (None, ".claude\\x"), (123, ".claude\\x")]:
    at("folder", "cwd=%r path=%r" % (cwd, path), "Write", {"file_path": path, "content": "x"}, GA, cwd=cwd)
# folder trick: grant in one folder, exec in another
for cwd in [PR2, PR + "\\src", W, PR + "\\jn", PR2 + "\\back", W + "\\jproj", PR + "\\src\\..\\", None, ""]:
    at("folder", "pytest -q cwd=%r" % (cwd,), "Bash", {"command": "pytest -q"}, GW, cwd=cwd)
# session tricks
at("session", "no record", "Write", {"file_path": "src/a.py", "content": "x"}, None, sess="nogrant-sess")
at("session", "missing session id", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess=("__MISSING__"))
at("session", "None session id", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess=("__NONE__"))
at("session", "int session id", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess=("__INT__"))
at("session", "list session id", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess=("__LIST__"))
at("session", "path-like session id", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess="..\\..\\x")
at("session", "session id with NUL", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess="s\x00t")
at("session", "session id 100k", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess="Z" * 100000)
at("session", "session id CON", "Write", {"file_path": "src/a.py", "content": "x"}, GW, sess="CON")
# slow inputs
at("slow", "pathological glob", "Write", {"file_path": "a" * 5000, "content": "x"}, "승인: 수정 " + "a*" * 11 + "b", sess=None)
at("slow", "pathological glob **", "Write", {"file_path": "/".join(["a"] * 3000) + "/c", "content": "x"}, "승인: 수정 " + "**/a/" * 6 + "b")
at("slow", "pathological ?*", "Write", {"file_path": "a" * 20000, "content": "x"}, "승인: 수정 " + "a?" * 40 + "*b")
at("slow", "huge command", "Bash", {"command": "pytest -q " + "x" * 2_000_000})
at("slow", "huge content", "Write", {"file_path": "src/a.py", "content": "x" * 5_000_000})
at("slow", "deep dotdot", "Write", {"file_path": "../" * 20000 + "x", "content": "x"}, GA)
at("slow", "deep path", "Write", {"file_path": "src/" + "a/" * 30000 + "x", "content": "x"}, GA)
at("slow", "huge grant prompt", "Write", {"file_path": "src/a.py", "content": "x"}, "승인: 수정 src/**" + ", src/x" * 20000)
at("slow", "300 star glob grant", "Write", {"file_path": "src/a.py", "content": "x"}, "승인: 수정 " + "*" * 300)
# prompt-level state attacks
at("state", "grant then revoke", "Write", {"file_path": "src/a.py", "content": "x"}, GW, pre=["승인 취소"])
at("state", "grant then read-only", "Write", {"file_path": "src/a.py", "content": "x"}, GW, pre=["읽기만 해줘"])
at("state", "grant then no-modify", "Write", {"file_path": "src/a.py", "content": "x"}, GW, pre=["수정하지 마"])
at("state", "grant then prompt-only", "Bash", {"command": "pytest -q"}, GW, pre=["프롬프트만 만들어줘"])
at("state", "grant split in two msgs", "Write", {"file_path": "src/a.py", "content": "x"}, "승인: 수정", pre=["src/**"])
at("state", "task end", "Bash", {"command": "pytest -q"}, "승인: 실행 pytest -q · 기간 작업", pre=["작업 종료"])
at("state", "revoke english", "Write", {"file_path": "src/a.py", "content": "x"}, GW, pre=["grant revoke"])
at("state", "restriction release then restricted write", "Write", {"file_path": "src/a.py", "content": "x"}, GW, pre=["읽기만 해줘", "제한 해제"])

# ---------------- run ----------------
if __name__ == "__main__":
    out = []
    t0 = time.time()
    for i, a in enumerate(A, 1):
        S = W + "\\state_att\\" + "%03d" % i
        shutil.rmtree(S, ignore_errors=True); os.makedirs(S)
        sid = a["sess"] if a["sess"] is not None else "att-%03d" % i
        sidv = sid
        if sid == "__MISSING__": sidv = "__MISSING__"
        gid = "att-%03d" % i if a["sess"] in ("__MISSING__", "__NONE__", "__INT__", "__LIST__") else sid
        gsid = gid
        if a["sess"] == "nogrant-sess": gsid = None
        cwd = a["cwd"]
        # prompts
        if a["grant"] and gsid is not None:
            call({"hook_event_name": "UserPromptSubmit", "session_id": gsid, "prompt": a["grant"], "cwd": PR if cwd in (None, "", ".", "src") or not isinstance(cwd, str) else (PR if a["kind"] != "folder" else PR)}, S)
        for p in a["pre"]:
            call({"hook_event_name": "UserPromptSubmit", "session_id": gsid, "prompt": p, "cwd": PR}, S)
        ev = {"hook_event_name": "PreToolUse", "session_id": gsid if gsid else sid, "tool_name": a["tool"], "tool_input": a["input"], "permission_mode": a["mode"], "cwd": cwd}
        if a["mode"] is None: ev.pop("permission_mode")
        if a["sess"] == "__MISSING__": ev.pop("session_id")
        if a["sess"] == "__NONE__": ev["session_id"] = None
        if a["sess"] == "__INT__": ev["session_id"] = 12345
        if a["sess"] == "__LIST__": ev["session_id"] = ["x"]
        if a["kind"] == "session" and a["sess"] and not a["sess"].startswith("__") and a["sess"] != "nogrant-sess": ev["session_id"] = a["sess"]
        r = call(ev, S)
        out.append(dict(id="A%03d" % i, kind=a["kind"], desc=a["desc"], tool=a["tool"], input={k: (v if not isinstance(v, str) or len(v) < 200 else v[:100] + "...len%d" % len(v)) for k, v in a["input"].items()}, grant=a["grant"][:80] if a["grant"] else None, cwd=cwd, mode=a["mode"], decision=r["decision"], rc=r["rc"], secs=r["secs"], reason=r["out"][:160], err=r["err"]))
    with open(EV + "\\attacks-results.jsonl", "w", encoding="utf-8") as f:
        for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(out), Counter(o["decision"] for o in out), "rc2", sum(o["rc"] == 2 for o in out), "slow", [(o["id"], o["secs"]) for o in out if o["secs"] > 2], "max", max(o["secs"] for o in out), round(time.time() - t0))
    for o in out:
        if o["decision"] == "allow": print(o["id"], o["kind"], o["desc"], "|", o["grant"], "|", o["cwd"] if o["kind"] == "folder" else "")
