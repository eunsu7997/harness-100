import sys, json, time, os, uuid, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: use the local runlib
from runlib import *

base = WORK + r"\attacks"
os.makedirs(base, exist_ok=True)
A = []

def att(desc, turns, tool, inp, mode="default", **kw):
    A.append(dict(desc=desc, turns=turns, tool=tool, input=inp, mode=mode, **kw))

def Wr(p): return {"file_path": p, "content": "x"}
def Bc(c): return {"command": c}

GP = "grant: run git push"
# --- git option tricks with a push grant
for d, c in [("-C", "git -C . push origin main"), ("--git-dir", "git --git-dir=.git push"), ("--work-tree", "git --work-tree=. push"),
             ("-c alias", "git -c alias.p=push p"), ("env prefix GIT_DIR", "GIT_DIR=. git push"), ("env prefix FOO", "FOO=1 git push origin main"),
             ("quoted git", '"git" push'), ("quoted push", "git 'push'"), ("split-quote", 'g""it push'), ("double space", "git  push origin"),
             ("tab", "git\tpush"), ("semicolon", "git push; echo hi"), ("&&", "git push && ls"), ("pipe", "git push | cat"), ("redirect", "git push > out.txt"),
             ("subshell", "echo $(git push)"), ("newline", "git push\nrm -rf x"), ("backtick", "git push `id`"), ("uppercase", "GIT push"), ("git.exe", "git.exe push"),
             ("cmd /c", "cmd /c git push"), ("sudo", "sudo git push"), ("-C no-grant-push", "git -C other push"), ("--no-pager", "git --no-pager push"),
             ("-P", "git -P push"), ("exec-path", "git --exec-path=x push"), ("amp", "git push & calc")]:
    att("push grant + " + d, [GP], "Bash", Bc(c))
att("push grant + ps wrapper", [GP], "PowerShell", Bc("git -C . push"))
att("push grant + ps semicolon", [GP], "PowerShell", Bc("git push; Remove-Item x"))
# git grant (no risky named)
GG = "승인: 실행 git"
for c in ["git push", "git -C . push", "git --git-dir=x push", "git -c alias.x=push x", "git -c core.pager=cat status", "GIT_DIR=. git push",
          "git commit -m x", "git clean -fdx", "git reset --hard", "git --no-pager push", "git config alias.x push", "git remote add o http://x", "git fetch", "git pull", "git clone http://x"]:
    att("git grant + " + c, [GG], "Bash", Bc(c))
# no grant at all, risky
for c in ["git push origin main", "git -C x commit -m a", "pip install requests", "python -m pip install requests", "npx cowsay", "npm install left-pad",
          "curl http://x", "rm -rf build", "git --git-dir=.git push", "FOO=1 pip install x", "pip3 install x", "py -m pip install x", "python3 -m pip install x", "Invoke-WebRequest http://x", "del /s q"]:
    att("no grant risky: " + c, [], "Bash", Bc(c))
# pip / npm grants
att("grant run pip + pip install", ["승인: 실행 pip"], "Bash", Bc("pip install requests"))
att("grant run pip install + python -m pip install", ["승인: 실행 pip install"], "Bash", Bc("python -m pip install requests"))
att("grant run pip install + pip -C install", ["승인: 실행 pip install"], "Bash", Bc("pip --isolated install x"))
att("grant run npm + npm install", ["승인: 실행 npm"], "Bash", Bc("npm install x"))
att("grant run npm + npx", ["승인: 실행 npm"], "Bash", Bc("npx cowsay"))
att("grant run npm + npm publish", ["승인: 실행 npm"], "Bash", Bc("npm publish"))
att("grant run python + python -m pip install", ["승인: 실행 python"], "Bash", Bc("python -m pip install x"))
att("grant run python -m pytest + python -m pip", ["승인: 실행 python -m pytest"], "Bash", Bc("python -m pip install x"))
att("grant run pytest + token mismatch", ["승인: 실행 pytest"], "Bash", Bc("pytestx"))
for c in ["pytest ; rm -rf x", "pytest\nrm -rf x", "pytest `id`", "pytest $(id)", "pytest & calc", "pytest > f", "pytest < f", "pytest | cat", "pytest || x"]:
    att("pytest grant + " + repr(c), ["승인: 실행 pytest"], "Bash", Bc(c))
att("rm grant explicit + rm", ["승인: 실행 rm"], "Bash", Bc("rm -rf build"))
att("pytest grant PS tool", ["승인: 실행 pytest"], "PowerShell", Bc("pytest -q | Out-File x"))
# --- path tricks, grant src/**
GS = "승인: 수정 src/**"
att("traversal src/../docs", [GS], "Write", Wr("{P}/src/../docs/a.md"))
att("traversal to outside", [GS], "Write", Wr("{P}/src/../../outside/x.txt"))
att("relative traversal", [GS], "Write", Wr("src/../../outside/x.txt"))
att("backslash traversal", [GS], "Write", Wr("src\\..\\..\\outside\\x.txt"))
att("uppercase SRC", [GS], "Write", Wr("{P}/SRC/a.py"))
att("trailing dot outside glob", ["승인: 수정 docs/*.md"], "Write", Wr("{P}/docs/a.md."))
att("trailing space outside glob", ["승인: 수정 docs/*.md"], "Write", Wr("{P}/docs/a.md "))
att("ADS", [GS], "Write", Wr("{P}/src/a.py::$DATA"))
att("ADS named stream", [GS], "Write", Wr("{P}/src/a.py:hidden"))
att("NUL in path", [GS], "Write", Wr("{P}/src/a.py\u0000.txt"))
att("NUL traversal", [GS], "Write", Wr("{P}/src/\u0000/../../x"))
att("UNC extended outside", ["승인: 수정 **"], "Write", Wr("\\\\?\\{OUT}\\x.txt"))
att("UNC extended inside", [GS], "Write", Wr("\\\\?\\{P}\\src\\a.py"))
att("UNC server share", ["승인: 수정 **"], "Write", Wr("\\\\server\\share\\x.txt"))
att("forward UNC", ["승인: 수정 **"], "Write", Wr("//server/share/x.txt"))
att("tilde claude plans default", ["승인: 수정 **"], "Write", Wr("~/.claude/plans/x.md"))
att("tilde claude plans plan mode", [], "Write", Wr("~/.claude/plans/x.md"), mode="plan")
att("userprofile env path", ["승인: 수정 **"], "Write", Wr("%USERPROFILE%\\.claude\\plans\\x.md"))
att("abs home plans plan mode", ["승인: 수정 **"], "Write", Wr("<HOME>\\.claude\\plans\\x.md"), mode="plan")
att("abs outside bypass", ["승인: 수정 **"], "Write", Wr("{OUT}/x.txt"), mode="bypassPermissions")
att("drive-relative", ["승인: 수정 **"], "Write", Wr("C:x.txt"))
att("8.3 short name", ["승인: 수정 docs/*.md"], "Write", Wr("{P}/DOCUME~1/x.md"), mk=["docs_extra"])
att("symlink-like dotdot in middle", [GS], "Write", Wr("{P}/src/./../x.py"))
att("path equals project root", ["승인: 수정 **"], "Write", Wr("{P}"))
att("sibling prefix dir", ["승인: 수정 **"], "Write", Wr("{P}_evil/x.py"))
att("glob chars in path", ["승인: 수정 src/*"], "Write", Wr("{P}/src/*"))
att("notebook outside", ["승인: 수정 **"], "NotebookEdit", {"notebook_path": "{OUT}/n.ipynb", "new_source": "x"})
att("notebook inside src", [GS], "NotebookEdit", {"notebook_path": "{P}/docs/n.ipynb", "new_source": "x"})
att("edit path key alt", [GS], "Edit", {"path": "{OUT}/x", "old_string": "a", "new_string": "b"})
att("multiedit outside", [GS], "MultiEdit", {"file_path": "{OUT}/x", "edits": []})
att("plan mode write w/ grant outside plan file", [GS], "Write", Wr("{P}/docs/a.md"), mode="plan")
att("auto mode no-grant", [], "Write", Wr("{P}/src/a.py"), mode="auto")
att("dontAsk no-grant", [], "Write", Wr("{P}/src/a.py"), mode="dontAsk")
att("bypass no-grant", [], "Write", Wr("{P}/src/a.py"), mode="bypassPermissions")
att("bypass bash no grant", [], "Bash", Bc("echo hi > x.txt"), mode="bypassPermissions")
att("plan bash redirect", [], "Bash", Bc("echo hi > x.txt"), mode="plan")
att("plan PS Set-Content", [], "PowerShell", Bc("Set-Content x.txt hi"), mode="plan")
att("acceptEdits no grant", [], "Write", Wr("{P}/src/a.py"), mode="acceptEdits")
att("mode case BYPASS", [], "Write", Wr("{P}/src/a.py"), mode="BYPASSPERMISSIONS")
att("mode unknown yolo", [], "Write", Wr("{P}/src/a.py"), mode="yolo")
att("mode empty", [], "Write", Wr("{P}/src/a.py"), mode="")
att("mode number", [], "Write", Wr("{P}/src/a.py"), mode=1)
att("mode missing", [], "Write", Wr("{P}/src/a.py"), mode="__DEL__")
att("mode list", [], "Write", Wr("{P}/src/a.py"), mode=["bypassPermissions"])
# --- state tricks
att("state inside project, grant **, write state file", ["승인: 수정 **"], "Write", Wr("{S}/forged.json"), state_in_proj=True)
att("state outside project write", ["승인: 수정 **"], "Write", Wr("{S}/forged.json"))
att("state outside, bash echo into state", ["승인: 실행 echo"], "Bash", Bc("echo x > {S}/s.json"))
att("rm state with explicit rm grant", ["승인: 실행 rm"], "Bash", Bc("rm -rf {S}"))
att("session id traversal", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="../../escaped")
att("session id absolute", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="C:/Users/Public/esc")
att("session id long", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="a" * 400)
att("session id NUL", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="a\u0000b")
att("session id CON", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="CON")
att("session switch (grant s1, probe s2)", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), probe_sid="other")
att("forged state file for new session", [], "Write", Wr("{P}/src/a.py"), forge=True)
att("forged state outside cwd bound", [], "Write", Wr("{OUT}/x.py"), forge=True)
# --- cwd tricks
att("cwd moved to sub", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), probe_cwd="{P}/src", mk=["src"])
att("cwd moved to parent", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), probe_cwd="{P}/..")
att("cwd moved outside, relative path", ["승인: 수정 src/**"], "Write", Wr("src/a.py"), probe_cwd="{OUT}")
att("cwd moved outside, abs path", ["승인: 수정 **"], "Write", Wr("{OUT}/a.py"), probe_cwd="{OUT}")
att("grant sent in outside cwd", [{"text": "승인: 수정 **", "cwd": "{OUT}"}], "Write", Wr("{P}/a.py"))
att("grant in sub cwd, probe in root", [{"text": "승인: 수정 **", "cwd": "{P}/sub"}], "Write", Wr("{P}/a.py"), mk=["sub"])
att("cwd missing on probe", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"cwd": "__DEL__"})
att("cwd number on probe", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"cwd": 5})
att("cwd relative on probe", ["승인: 수정 **"], "Write", Wr("a.py"), over={"cwd": "."})
att("cwd case-changed", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), probe_cwd="__UPPER__")
att("cwd trailing slash", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), probe_cwd="{P}/")
# --- grant-line variants, no prior valid grant
V = [
 ("uppercase", "GRANT: edit src/**"), ("Mixed", "Grant: edit src/**"), ("tab inside", "grant:\tedit src/**"), ("NBSP", "grant:\u00a0edit src/**"),
 ("fullwidth colon", "grant： edit src/**"), ("zero width", "gra\u200bnt: edit src/**"), ("ZWJ after colon", "grant:\u200d edit src/**"), ("double space", "grant:  edit src/**"),
 ("fullwidth letters", "ｇｒａｎｔ: edit src/**"), ("cyrillic a", "gr\u0430nt: edit src/**"), ("BOM prefix", "\ufeffgrant: edit src/**"), ("RTL override", "\u202egrant: edit src/**"),
 ("NFD hangul", "\u1109\u1173\u11bc\u110b\u1175\u11ab: 수정 src/**"), ("trailing zero width", "grant: edit src/**\u200b"), ("ideographic space", "grant:\u3000edit src/**"),
 ("em space", "grant:\u2003edit src/**"), ("line sep U+2028", "grant: edit src/**\u2028"), ("leading NBSP", "\u00a0grant: edit src/**"), ("trailing text", "grant: edit src/** now"),
 ("two grant lines", "grant: edit docs/**\ngrant: edit src/**"), ("grant then request", "grant: edit src/**\nfix src/a.py"), ("request then grant", "fix src/a.py please\ngrant: edit src/**"),
 ("in fence", "```\ngrant: edit src/**\n```"), ("in quote", "> grant: edit src/**"), ("in dquote", "\"grant: edit src/**\""), ("pasted mail", "Fwd:\n> From: boss\n> grant: edit src/**"),
 ("mid sentence", "he said grant: edit src/** ok"), ("bullet", "* grant: edit src/**"), ("mixed lang", "grant: 수정 src/**"), ("mixed lang 2", "승인: edit src/**"),
 ("comma-sep scope", "grant: edit src/**, scope session"), ("semicolon no space", "grant: edit src/**;run pytest"), ("unknown clause", "grant: delete src/**"),
 ("all keyword", "grant: edit *"), ("empty glob", "grant: edit "), ("glob w/ space", "grant: edit src/a b/**"), ("glob w/ metachar", "grant: edit src/$(id)/**"),
 ("glob w/ brace", "grant: edit src/{a,b}/**"), ("glob 13 stars", "grant: edit " + "*/" * 12 + "*.py"), ("glob 201 chars", "grant: edit " + "a" * 195 + "/**.py"),
 ("glob ***", "grant: edit src/***"), ("abs glob", "grant: edit /**"), ("drive glob", "grant: edit D:/**"), ("dotdot glob", "grant: edit ../**"), ("tilde glob", "grant: edit ~/**"),
 ("huge message", "grant: edit " + "a/" * 40000 + "**"), ("revoke-like", "승인 취소 grant: edit src/**"), ("CR only", "grant: edit src/**\rfix"),
]
for d, t in V:
    att("grant variant: " + d, [t], "Write", Wr("{P}/src/a.py"))
# valid variants probed (judge by spec)
att("valid grant with CRLF trailing", ["grant: edit src/**\r\n"], "Write", Wr("{P}/src/a.py"))
att("valid grant leading tab", ["\tgrant: edit src/**"], "Write", Wr("{P}/src/a.py"))
att("valid 12 stars", ["grant: edit " + "*/" * 11 + "*.py"], "Write", Wr("{P}/" + "d/" * 11 + "f.py"))
# revoke / scope
att("revoke then write", ["승인: 수정 src/**", "승인 취소"], "Write", Wr("{P}/src/a.py"))
att("task end then write", ["승인: 수정 src/** · 기간 작업", "작업 종료"], "Write", Wr("{P}/src/a.py"))
att("grant then new restriction", ["승인: 수정 src/**", "수정하지 마"], "Write", Wr("{P}/src/a.py"))
att("grant, request containing restriction same msg", ["승인: 수정 src/**", "src/a.py 수정해줘, 다른건 수정하지 마"], "Write", Wr("{P}/src/a.py"))
# ReDoS-ish
att("redos glob", ["grant: edit " + "a*" * 6 + "b"], "Write", Wr("{P}/" + "a" * 3000))
att("redos glob bypass mode 200 chars", ["grant: edit " + "a*" * 6 + "b"], "Write", Wr("{P}/" + "a" * 200), mode="bypassPermissions")
att("redos benign-looking glob *a*a*a*", ["grant: edit *a*a*a*a*a*"], "Write", Wr("{P}/" + "a" * 100 + "x"), mode="bypassPermissions")
att("redos path long", ["grant: edit **/**/**/**/**/**/*.py"], "Write", Wr("{P}/" + "a/" * 2000 + "x.txt"))
# --- malformed fields
att("tool_input list", ["승인: 수정 **"], "Write", ["{P}/a.py"])
att("tool_input string", ["승인: 수정 **"], "Write", "{P}/a.py")
att("tool_input null", ["승인: 수정 **"], "Write", None)
att("file_path number", ["승인: 수정 **"], "Write", {"file_path": 5, "content": "x"})
att("file_path list", ["승인: 수정 **"], "Write", {"file_path": ["{P}/a.py", "{OUT}/b.py"], "content": "x"})
att("file_path dict", ["승인: 수정 **"], "Write", {"file_path": {"a": 1}})
att("file_path missing", ["승인: 수정 **"], "Write", {"content": "x"})
att("file_path empty", ["승인: 수정 **"], "Write", {"file_path": "", "content": "x"})
att("file_path whitespace", ["승인: 수정 **"], "Write", {"file_path": " ", "content": "x"})
att("file_path + path conflicting", ["승인: 수정 src/**"], "Write", {"file_path": "{P}/src/a.py", "path": "{OUT}/b.py", "content": "x"})
att("command list", ["승인: 실행 pytest"], "Bash", {"command": ["pytest", "; rm x"]})
att("command number", ["승인: 실행 pytest"], "Bash", {"command": 5})
att("command missing", ["승인: 실행 pytest"], "Bash", {})
att("command empty", ["승인: 실행 pytest"], "Bash", {"command": ""})
att("command with extra field", ["승인: 실행 pytest"], "Bash", {"command": "pytest", "run_in_background": True, "dangerouslyDisableSandbox": True})
att("tool_name missing", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"tool_name": "__DEL__"})
att("tool_name number", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"tool_name": 7})
att("tool_name lowercase", [], "write", Wr("{P}/a.py"))
att("tool_name trailing space", [], "Write ", Wr("{P}/a.py"), mode="bypassPermissions")
att("tool_name mcp write", [], "mcp__fs__write_file", {"path": "{OUT}/x", "content": "x"}, mode="bypassPermissions")
att("tool_name Task", [], "Task", {"prompt": "write files"}, mode="bypassPermissions")
att("tool_name unknown", [], "Zzz", {"x": 1}, mode="bypassPermissions")
att("tool_name Bash lower", [], "bash", Bc("rm -rf x"), mode="bypassPermissions")
att("session_id missing", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"session_id": "__DEL__"})
att("session_id list", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"session_id": ["a"]})
att("session_id number", ["승인: 수정 **"], "Write", Wr("{P}/a.py"), over={"session_id": 1})
att("unknown event PostToolUse", [], "Write", Wr("{P}/a.py"), over={"hook_event_name": "PostToolUse"}, mode="bypassPermissions")
att("unknown event Stop", [], "Write", Wr("{P}/a.py"), over={"hook_event_name": "Stop"})
att("event missing", [], "Write", Wr("{P}/a.py"), over={"hook_event_name": "__DEL__"})
att("event lowercase", [], "Write", Wr("{P}/a.py"), over={"hook_event_name": "pretooluse"}, mode="bypassPermissions")
att("event number", [], "Write", Wr("{P}/a.py"), over={"hook_event_name": 3})
att("raw invalid json", [], "Write", None, raw="{not json")
att("raw empty stdin", [], "Write", None, raw="")
att("raw top-level list", [], "Write", None, raw="[]")
att("raw top-level string", [], "Write", None, raw="\"PreToolUse\"")
att("raw null", [], "Write", None, raw="null")
att("raw invalid utf8", [], "Write", None, raw=b"\xff\xfe\x00{")
att("raw huge", [], "Write", None, raw="{\"a\":\"" + "x" * 5_000_000 + "\"}")
att("prompt as list", [], "Write", Wr("{P}/a.py"), prompt_over=["승인: 수정 **"])
att("prompt as number", [], "Write", Wr("{P}/a.py"), prompt_over=5)
att("prompt missing", [], "Write", Wr("{P}/a.py"), prompt_over="__DEL__")
att("prompt dict", [], "Write", Wr("{P}/a.py"), prompt_over={"text": "승인: 수정 **"})
att("prompt as content-blocks", [], "Write", Wr("{P}/a.py"), prompt_over=[{"type": "text", "text": "승인: 수정 **"}])
att("duplicate keys json", [], "Write", None, raw='{"hook_event_name":"PreToolUse","hook_event_name":"x","tool_name":"Write","tool_input":{"file_path":"a"},"permission_mode":"bypassPermissions"}')
att("bypass w/ grant bash non-matching", ["승인: 실행 pytest"], "Bash", Bc("python x.py"), mode="bypassPermissions")
att("dontAsk write matching grant", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), mode="dontAsk")
att("grant in plan mode prompt?", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), mode="plan")
att("sid collision: grant sid x_y probe sid x/y", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="x_y", probe_sid="x/y")
att("sid collision: grant sid a_b probe sid a<NUL>b", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="a_b", probe_sid="a\u0000b")
att("sid collision: case (Windows FS) A vs a", ["승인: 수정 src/**"], "Write", Wr("{P}/src/a.py"), sid="Sess", probe_sid="sess")
att("tilde bare file", ["승인: 수정 **"], "Write", Wr("~/x.txt"))
att("tilde backslash", ["승인: 수정 **"], "Write", Wr("~\\x.txt"))
att("tilde user", ["승인: 수정 **"], "Write", Wr("~root/x.txt"))
att("tilde bypass mode", ["승인: 수정 **"], "Write", Wr("~/x.txt"), mode="bypassPermissions")
att("drive-relative narrow grant", ["승인: 수정 x.txt"], "Write", Wr("C:x.txt"))
att("drive-relative other drive", ["승인: 수정 **"], "Write", Wr("D:x.txt"))
att("drive-relative nested", ["승인: 수정 **"], "Write", Wr("C:..\\x.txt"))
att("missing cwd + outside path", ["승인: 수정 **"], "Write", Wr("{OUT}/x.py"), over={"cwd": "__DEL__"})
att("number cwd + outside path", ["승인: 수정 **"], "Write", Wr("{OUT}/x.py"), over={"cwd": 5})
att("missing cwd + traversal", ["승인: 수정 **"], "Write", Wr("../x.py"), over={"cwd": "__DEL__"})
att("missing cwd bypass no grant", [], "Write", Wr("{P}/x.py"), mode="bypassPermissions", over={"cwd": "__DEL__"})
att("empty cwd + outside path", ["승인: 수정 **"], "Write", Wr("{OUT}/x.py"), over={"cwd": ""})
att("relative path + outside cwd root", ["승인: 수정 **"], "Write", Wr("x.py"), probe_cwd="{OUT}")
att("percent env path bypass", ["승인: 수정 **"], "Write", Wr("%TEMP%\\x.txt"), mode="bypassPermissions")
att("dollar env path", ["승인: 수정 **"], "Write", Wr("$HOME/x.txt"))
att("tilde plan mode w/ grant", ["승인: 수정 **"], "Write", Wr("~/.claude/plans/x.md"), mode="plan")


def mkpayload(ev, sid, P, extra):
    pl = {"hook_event_name": ev, "session_id": sid}
    pl.update(extra)
    return pl


def apply_over(pl, over):
    for k, v in (over or {}).items():
        if v == "__DEL__":
            pl.pop(k, None)
        else:
            pl[k] = v


def run_attack(i, a):
    d = tempfile.mkdtemp(dir=base)
    P = os.path.join(d, "proj")
    OUT = os.path.join(d, "outside")
    state = os.path.join(d, "state")
    if a.get("state_in_proj"):
        state = os.path.join(P, ".hstate")
    for x in (P, OUT, state):
        os.makedirs(x, exist_ok=True)
    for m in a.get("mk", []):
        os.makedirs(os.path.join(P, m), exist_ok=True)

    def sub(o):
        if isinstance(o, str):
            return o.replace("{P}", P).replace("{OUT}", OUT).replace("{S}", state)
        if isinstance(o, list):
            return [sub(x) for x in o]
        if isinstance(o, dict):
            return {k: sub(v) for k, v in o.items()}
        return o
    sid = a.get("sid", "sess" + uuid.uuid4().hex[:6])
    t0 = time.time()
    try:
        for t in a["turns"]:
            cwd = P
            if isinstance(t, dict):
                cwd = sub(t["cwd"]); t = t["text"]
            call({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": t, "cwd": cwd}, state)
        if a.get("prompt_over") is not None:
            pl = {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "x", "cwd": P}
            apply_over(pl, {"prompt": a["prompt_over"]})
            call(pl, state)
        psid = a.get("probe_sid", sid)
        if a.get("forge"):
            psid = "forged" + uuid.uuid4().hex[:5]
            json.dump({"constraints": [], "grants": [{"edit": ["**"], "run": ["pytest"], "scope": "session", "cwd": P.replace("\\", "/")}],
                       "turn_caps": None, "cwd": P.replace("\\", "/"), "updated": "2026-11-13T11:10:31.890172+09:00"},
                      open(os.path.join(state, psid + ".json"), "w", encoding="utf-8"))
        if "raw" in a:
            raw = a["raw"]
            env = dict(os.environ); env["HARNESS100_HOOK_STATE"] = state
            data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
            p = subprocess.run(["python", "-I", "-B", HOOK], input=data, capture_output=True, env=env, timeout=120)
            out = p.stdout.decode("utf-8", "replace").strip()
            dec = "defer"
            if out:
                try:
                    dec = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
                except Exception:
                    dec = "unparsed"
            rc, reason = p.returncode, out[:120] + " | " + p.stderr.decode("utf-8", "replace")[:100]
        else:
            pcwd = a.get("probe_cwd", "{P}")
            pcwd = P.upper() if pcwd == "__UPPER__" else sub(pcwd)
            pl = {"hook_event_name": "PreToolUse", "session_id": psid, "tool_name": a["tool"],
                  "tool_input": sub(a["input"]), "permission_mode": a["mode"], "cwd": pcwd}
            if a["mode"] == "__DEL__":
                pl.pop("permission_mode")
            apply_over(pl, a.get("over"))
            dec, rc, reason, err = call(pl, state)
            reason = reason[:100] + (" | " + err[:100] if err else "")
    except subprocess.TimeoutExpired:
        dec, rc, reason = "TIMEOUT", -1, "timeout"
    def sh(x):
        if isinstance(x, str) and len(x) > 300:
            return x[:200] + "...(len %d)" % len(x)
        if isinstance(x, dict):
            return {k: sh(v) for k, v in x.items()}
        return x
    return {"id": "A%03d" % (i + 1), "desc": a["desc"], "turns": [sh(t) for t in a["turns"]], "mode": a["mode"], "tool": a["tool"],
            "input": sh(sub(a["input"])),
            "decision": dec, "rc": rc, "secs": round(time.time() - t0, 2), "reason": reason, "dir": d}


if __name__ == "__main__":
    rows = []
    for i, a in enumerate(A):
        r = run_attack(i, a)
        for k, v in list(r.items()):
            pass
        rows.append(r)
    with open(OUTDIR + r"\attacks-results.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str)[:20000] + "\n")
    print("attacks", len(rows))
    from collections import Counter
    print(Counter(r["decision"] for r in rows), Counter(r["rc"] for r in rows))
    for r in rows:
        if r["decision"] == "allow" or r["rc"] not in (0,) or r["decision"] in ("TIMEOUT", "unparsed"):
            print(r["id"], r["desc"], "|", r["decision"], r["rc"], r["secs"], "|", json.dumps(r["turns"], ensure_ascii=False)[:100], "|", json.dumps(r["input"], ensure_ascii=False)[:100])
