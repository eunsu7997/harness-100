"""Claude Code hook (v3.1-CC): the router chooses what to do; grants and Claude Code decide what may be done.

Register for UserPromptSubmit and PreToolUse (see platforms/claude-code/settings.snippet.json).

Decisions (docs/GRANT-SPEC.md):
- allow  : ONLY in grant_decision(), when the tool call exactly matches an explicit grant line written by the user
           ("승인: 수정 <glob> · 실행 <명령 접두>"). No sentence interpretation can produce allow.
- deny   : user restrictions ("읽기만", "수정하지 마", "프롬프트만" ...), a recognised read-only/answer turn,
           protected hook state, or a write/execute outside every grant in a permission mode with no prompt
           (auto, dontAsk, bypassPermissions; writes in acceptEdits).
- defer  : everything else -> Claude Code's own permission flow (prompt, permission rules).
- Read/Glob/Grep, read-only Bash, Skill and skill-file reads have no side effects and are never denied.
- Fail closed: an unreadable state file restricts everything; an internal error exits 2 (blocks the tool).
"""

import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))

from harness100 import grant as grants_mod  # noqa: E402
from harness100.constraints import is_confirm_clause, normalize, sentences, wants_unlock  # noqa: E402
from harness100.ledger import default_state_dir  # noqa: E402

READ_TOOLS = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
NET_TOOLS = {"WebFetch", "WebSearch"}
SAFE_META = {"TodoWrite", "AskUserQuestion", "ToolSearch", "Skill"}
SHELL_TOOLS = {"Bash", "PowerShell"}
DENY_CONSTRAINTS = {"read_only", "analyze_only", "prompt_only", "no_modify", "no_create", "no_execute", "no_deploy",
                    "no_delete", "no_install", "no_network", "no_commit"}
ALL_RESTRICTIONS = ["read_only", "no_modify", "no_create", "no_execute", "no_deploy", "no_delete", "no_install",
                    "no_network", "no_commit"]
NO_PROMPT_MODES = {"auto", "dontAsk", "bypassPermissions"}
KNOWN_MODES = {"default", "manual", "plan", "acceptEdits"} | NO_PROMPT_MODES  # "manual": CLI 2.1.x name of the prompting mode
READONLY_CMDS = {
    "ls", "dir", "cat", "head", "tail", "wc", "pwd", "echo", "printf", "grep", "egrep", "fgrep", "rg", "find", "file",
    "stat", "du", "df", "which", "where", "type", "sort", "uniq", "cut", "tr", "diff", "cmp", "sha256sum", "md5sum",
    "sha1sum", "tree", "basename", "dirname", "realpath", "date", "whoami", "cd", "true", "test", "[",
    "get-childitem", "gci", "get-content", "gc", "select-string", "sls", "get-item", "gi", "test-path",
    "get-location", "gl", "measure-object", "get-filehash", "resolve-path", "select-object", "sort-object",
    "where-object", "format-list", "format-table", "write-output", "out-string", "get-date",
}
DENY_OPTIONS = {
    "sort": re.compile(r"^(?:-o.*|--output.*|-[a-z]*o)$"),
    "tree": re.compile(r"^-o$|^--output"),
    "find": re.compile(r"^-(?:exec|execdir|ok|okdir|delete|fprint|fprint0|fprintf|fls)$"),
    "rg": re.compile(r"^--pre(?:-glob)?(?:=.*)?$"),
    "date": re.compile(r"^(?:-s.*|--set.*)$"),
    "get-content": re.compile(r"^-(?:wait|stream)$"),
}
PATTERNS = [
    ("deploy", r"\bgit\s+push\b|\b(?:vercel|netlify|heroku)\b|\bfirebase\s+deploy\b|\baxhub\s+deploy\b|"
               r"\bkubectl\s+(?:apply|delete|rollout|scale)\b|\bterraform\s+(?:apply|destroy)\b|\bhelm\s+(?:install|upgrade)\b|"
               r"\bdocker\s+push\b|\bnpm\s+publish\b|\bgh\s+release\b|\bfly\s+deploy\b|\btwine\s+upload\b|"
               r"\b(?:deploy|publish|release)\b"),
    ("commit", r"\bgit\s+(?:commit|merge|rebase|tag|cherry-pick|am)\b"),
    ("delete", r"(?:^|[\s;&|(])(?:rm|rmdir|del|erase|rd|shred|unlink)\b|\bremove-item\b|\bgit\s+(?:clean|reset\s+--hard|checkout\s+--|restore)\b|"
               r"\bdrop\s+(?:table|database|schema|index)\b|\btruncate\b|\bdelete\s+from\b|\buninstall\b"),
    ("install", r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|i|add|ci)\b|\bpip3?\s+install\b|\buv\s+(?:pip|add|sync)\b|"
                r"\b(?:winget|choco|scoop|brew|cargo|go)\s+install\b|\bapt(?:-get)?\s+install\b|\binstall-module\b|\bnpx\b"),
    ("network", r"\b(?:curl|wget|invoke-webrequest|invoke-restmethod|iwr|irm|ssh|scp|sftp|rsync|ftp|nc|ncat|start-bitstransfer)\b|"
                r"\bgit\s+(?:fetch|pull|clone|ls-remote|submodule\s+update)\b|\bpip3?\s+download\b"),
]
RISKY = {"deploy", "delete", "install", "network", "commit"}
SKILL_DIRS = [Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills", Path.home() / ".codex" / "skills"]
BLOCKED_BY = {"no_modify": {"write", "create", "delete", "commit"}, "no_create": {"create"},
              "no_execute": {"execute", "deploy", "install"}, "no_deploy": {"deploy"}, "no_delete": {"delete"},
              "no_install": {"install"}, "no_network": {"network", "network_tool"}, "no_commit": {"commit"}}
UNLOCK_HINT = " (제한 해제: '제한 해제'만 단독 입력 / 범위 승인: '승인: 수정 <glob> · 실행 <명령>')"


def state_dir():
    return Path(os.environ.get("HARNESS100_HOOK_STATE") or (default_state_dir() / "claude-code-sessions"))


def state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")[:120]
    return state_dir() / f"{safe}.json"


def load_state(session_id):
    path = state_path(session_id)
    if not path.exists():
        return {"constraints": [], "grants": [], "present": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("constraints"), list) or not isinstance(data.get("grants", []), list):
            raise ValueError("bad state")
        return dict(data, present=True)
    except (OSError, ValueError):
        return {"constraints": list(ALL_RESTRICTIONS), "grants": [], "present": True, "corrupt": True}


def log(event):
    try:
        state_dir().mkdir(parents=True, exist_ok=True)
        with open(state_dir() / "hook-log.jsonl", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(event, time=datetime.now().astimezone().isoformat()), ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- tool classification (unchanged from v3.0.2)
def split_segments(command):
    return [seg.strip() for seg in re.split(r"\|\||&&|[;|&\n]", command) if seg.strip()]


def is_readonly_command(command):
    """Strict allowlist check. Returns (ok, reason)."""
    if not command.strip():
        return False, "empty command"
    if re.search(r">|<<|<\(|\$\(|`", command):
        return False, "redirection or substitution"
    for seg in split_segments(command):
        try:
            words = shlex.split(seg, posix=True)
        except ValueError:
            return False, "unparseable command"
        if not words:
            continue
        first = re.sub(r"\.exe$", "", os.path.basename(words[0])).lower()
        if first not in READONLY_CMDS:
            return False, f"not an allowlisted read command: {first}"
        rule = DENY_OPTIONS.get(first)
        if rule and any(rule.match(w.lower()) for w in words[1:]):
            return False, f"write/exec option for {first}"
        if first == "uniq" and len([w for w in words[1:] if not w.startswith("-")]) > 1:
            return False, "uniq with an output file"
    return True, "read-only"


def classify_command(command):
    ok, _ = is_readonly_command(command)
    if ok:
        return {"read"}
    actions = {"execute"}
    lowered = command.lower()
    for name, pattern in PATTERNS:
        if re.search(pattern, lowered):
            actions.add(name)
    if re.search(r">|\btee\b|\bsed\s+-[a-z]*i|\b(?:mv|cp|mkdir|touch|chmod|ln|new-item|set-content|add-content|out-file|copy-item|move-item)\b", lowered):
        actions.add("write")
    if re.search(r">|\btee\b|\b(?:cp|mkdir|touch|new-item|out-file|copy-item|set-content)\b", lowered):
        actions.add("create")
    return actions


def tool_actions(tool, tool_input):
    if tool in READ_TOOLS:
        return {"read"}
    if tool in WRITE_TOOLS:
        return {"write", "create"} if tool == "Write" else {"write"}
    if tool in NET_TOOLS:
        return {"network_tool"}
    if tool in SAFE_META:
        return set()
    if tool in SHELL_TOOLS:
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str) or not command.strip():
            return {"unknown"}
        return classify_command(command)
    if tool in ("Agent", "Task"):
        return {"delegate"}
    if tool.startswith("mcp__"):
        return {"mcp"}
    return {"unknown"}


def touches_hook_state(tool_input):
    text = json.dumps(tool_input, ensure_ascii=False).replace("\\\\", "/").lower()
    return (str(state_dir()).replace("\\", "/").lower() in text or "claude-code-sessions" in text
            or "claude_code_hook" in text)


# ---------------------------------------------------------------- decisions
def grant_decision(state, tool, tool_input, cwd):
    """The single place that can return "allow": an exact match with an explicit user grant."""
    if state.get("corrupt") or "confirm_first" in state.get("constraints", []):
        return None, None
    candidates = grants_mod.matches(state.get("grants", []), tool, tool_input, cwd)
    if candidates and tool in SHELL_TOOLS:
        # Rule A: a risky action (push/deploy/delete/network/install/commit) is allowed only when the grant names
        # that action; a bare program prefix ("승인: 실행 git") never covers it. Classification runs on the normalized
        # command (git global options removed, "python -m pip" -> "pip"); a risky command that needed normalizing
        # (-C, --git-dir, -c alias.* ...) is never allowed.
        command = tool_input.get("command", "")
        tokens, flags = grants_mod.normalize_command(command)
        risky = (classify_command(command) | classify_command(" ".join(tokens or []))) & RISKY
        if risky and (flags["global_opts"] or flags["config_override"]):
            candidates = []
        elif flags["config_override"]:
            candidates = []  # git -c alias.* / core.* can turn any subcommand into anything
        elif risky:
            candidates = [c for c in candidates if risky <= classify_command(c.split(" ", 1)[1])]
    clause = candidates[0] if candidates else None
    if clause:
        return "allow", f"사용자 승인 범위와 일치: {clause}"
    return None, None


def restriction_denial(constraints, acts):
    c = set(constraints)
    if not c & DENY_CONSTRAINTS:
        return None
    if c & {"read_only", "analyze_only", "prompt_only"} and acts - {"read"}:
        label = "프롬프트(텍스트)만" if "prompt_only" in c else "읽기·분석만"
        return f"사용자가 {label} 허용함: 쓰기·실행·배포·삭제·네트워크 차단" + UNLOCK_HINT
    for constraint, kinds in BLOCKED_BY.items():
        if constraint in c and acts & kinds:
            return f"사용자 제한 {constraint} 위반 행동 차단: {sorted(acts & kinds)}" + UNLOCK_HINT
    if acts & {"mcp", "unknown", "delegate"}:
        return "사용자 제한 활성 중: 부작용을 판정할 수 없는 도구 차단" + UNLOCK_HINT
    return None


def turn_scope_denial(turn_caps, acts):
    """Only a recognised read-only / answer turn narrows; an unrecognised request leaves turn_caps None."""
    if turn_caps is None:
        return None
    caps = set(turn_caps)
    if acts & {"write", "create", "commit"} and "write" not in caps:
        return "이번 요청(검수·질문·초안·붙여넣기 검토 등)의 범위에 파일 변경이 없음"
    if acts & {"execute", "install", "network"} and "execute" not in caps:
        return "이번 요청의 범위에 명령 실행이 없음"
    if "deploy" in acts and "deploy" not in caps:
        return "이번 요청은 배포·push를 포함하지 않음"
    if "delete" in acts and not caps & {"delete", "write"}:
        return "이번 요청의 범위에 삭제가 없음"
    return None


def mode_denial(mode, acts, tool):
    mutating = acts - {"read"}
    if not mutating:
        return None
    if mode not in KNOWN_MODES:
        return f"알 수 없는 권한 모드({mode}): 승인 범위 밖 변경·실행 차단"
    if mode in NO_PROMPT_MODES:
        return f"확인 창이 없는 모드({mode}): 승인 범위 밖 변경·실행 차단"
    if mode == "acceptEdits" and (tool in WRITE_TOOLS or acts & {"write", "create", "delete"}):
        return "acceptEdits 모드는 편집을 묻지 않음: 승인 범위 밖 파일 변경 차단"
    if mode == "plan" and (tool in WRITE_TOOLS or acts & {"write", "create", "delete"}):
        return "plan 모드의 쓰기(계획 파일 포함)는 확인 창 없이 실행됨: 승인 범위 밖 파일 변경 차단"
    return None


def invalid_input(tool, tool_input):
    """Fields the decision depends on must be strings; anything else cannot be judged."""
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return True
    for key in ("file_path", "notebook_path", "command", "path"):
        if key in tool_input and not isinstance(tool_input[key], str):
            return True
    if tool in WRITE_TOOLS and not isinstance(tool_input.get("file_path") or tool_input.get("notebook_path"), str):
        return True
    return tool in SHELL_TOOLS and not isinstance(tool_input.get("command"), str)


def outside_project(tool_input, cwd):
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(cwd, str) or not cwd:
        return True
    try:
        root = Path(cwd).resolve()
        path = Path(target)
        path = (path if path.is_absolute() else root / path).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return True
    return False


def decide(state, tool, tool_input, mode="default", cwd=None):
    if invalid_input(tool, tool_input):
        return "deny", "판정할 수 없는 입력 형식(문자열이 아닌 도구 이름·경로·명령)"
    acts = tool_actions(tool, tool_input)
    if acts - {"read"} and touches_hook_state(tool_input):
        return "deny", "Harness-100 상태·hook 파일은 변경할 수 없음"
    if tool in WRITE_TOOLS and outside_project(tool_input, cwd):
        return "deny", "작업 폴더 밖 파일 쓰기 차단(승인 범위는 프로젝트 안 상대 경로만)"
    if not acts - {"read"}:
        # Read/Glob/Grep, read-only Bash, Skill, TodoWrite have no side effects: never denied. A read-only command
        # that the user granted explicitly is allowed like any other granted call (no re-confirmation).
        return grant_decision(state, tool, tool_input, cwd) if tool in SHELL_TOOLS else (None, None)
    reason = restriction_denial(state.get("constraints", []), acts)
    if reason:
        return "deny", reason
    decision, why = grant_decision(state, tool, tool_input, cwd)
    if decision:
        return decision, why
    turn_caps = ["read"] if state.get("corrupt") else state.get("turn_caps")
    reason = turn_scope_denial(turn_caps, acts)
    if reason:
        return "deny", reason + " (승인하려면 '승인: 수정 <glob> · 실행 <명령>')"
    reason = mode_denial(mode, acts, tool)
    if reason:
        return "deny", reason
    return None, None


# ---------------------------------------------------------------- events
def on_prompt(payload):
    session, prompt = payload.get("session_id", ""), payload.get("prompt", "")
    if not isinstance(session, str):
        session = "invalid-session"
    if not isinstance(prompt, str):
        prompt = ""
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    state = load_state(session)
    constraints = set(state.get("constraints", []))  # a corrupt state loads as "everything restricted"
    grants = list(state.get("grants", []))
    turn_caps = state.get("turn_caps")
    # Rule B: only a message that is exactly one grant line is a grant (bound to this message's cwd).
    new_grants, revoke, task_end, rest = grants_mod.parse_prompt(prompt, cwd)
    if revoke:
        grants = []
    if task_end:
        grants = [g for g in grants if g.get("scope") != "task"]
    if new_grants:
        constraints = set()  # an explicit grant is the user's newer decision: earlier restrictions end here
        grants.extend(new_grants)
    if wants_unlock(prompt):
        constraints, turn_caps = set(), None
    elif rest:
        from harness100.router import route
        decision = route(rest)
        found = set(decision["constraints"])
        if not any(is_confirm_clause(sentence) for sentence in sentences(normalize(rest))):
            # confirm_first can also come from inference (unclear verb, unclear negation scope). Only the user's own
            # "ask me first" may suspend a grant; inference never denies here, so dropping it cannot widen anything.
            found.discard("confirm_first")
        constraints |= found
        ambiguous = decision["intent"] == "answer" and any("확정하지 못함" in r for r in decision["reasons"])
        if not ambiguous:  # unrecognised request: keep the previous scope (never widen) or none (never deny on it)

            turn_caps = decision["capabilities"]
    elif new_grants or revoke or task_end:
        turn_caps = None  # a message that only grants/revokes carries no task interpretation
    path = state_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"constraints": sorted(constraints), "grants": grants, "turn_caps": turn_caps,
              "cwd": cwd, "updated": datetime.now().astimezone().isoformat()}
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    log({"event": "UserPromptSubmit", "session": session, "constraints": record["constraints"], "grants": grants,
         "turn_caps": turn_caps, "new_grants": len(new_grants), "revoke": revoke})
    notes = []
    if grants:
        notes.append("[Harness-100] 승인 범위(재확인 없이 진행): " + "; ".join(
            ", ".join([f"수정 {p}" for p in g["edit"]] + ["실행 " + " ".join(r) for r in g["run"]]) for g in grants))
    if constraints:
        notes.append(f"[Harness-100] 활성 사용자 제한: {', '.join(sorted(constraints))}. hook이 강제합니다.")
    if turn_caps is not None and not {"write", "execute"} <= set(turn_caps):
        notes.append(f"[Harness-100] 이번 요청의 작업 범위: {', '.join(turn_caps) or '답변만'}.")
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": " ".join(notes)}}


def on_tool(payload):
    session = payload.get("session_id", "")
    valid_session = isinstance(session, str)
    state = load_state(session if valid_session else "invalid-session")
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    mode = payload.get("permission_mode")
    mode = "default" if mode is None or mode == "" else mode if isinstance(mode, str) else "__invalid__"
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) and payload.get("cwd") else state.get("cwd")
    if not valid_session:
        decision, reason = "deny", "판정할 수 없는 입력 형식(session_id)"
    else:
        decision, reason = decide(state, tool, tool_input, mode, cwd)
    target = command = None
    if isinstance(tool_input, dict):
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        command = tool_input.get("command")
    log({"event": "PreToolUse", "session": session if valid_session else "invalid", "tool": tool if isinstance(tool, str) else repr(tool),
         "mode": mode, "mode_reported": "permission_mode" in payload, "decision": decision or "defer", "reason": reason,
         "target": target if isinstance(target, str) else None, "command": command[:200] if isinstance(command, str) else None,
         "cwd": cwd, "constraints": state.get("constraints", []), "grants": len(state.get("grants", [])),
         "corrupt": state.get("corrupt", False)})
    if not decision:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        raise ValueError("hook payload must be a JSON object")
    event = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if event not in ("UserPromptSubmit", "PreToolUse"):
        raise ValueError(f"unknown hook event {event!r}")  # fail closed (exit 2) instead of silently deferring
    result = on_prompt(payload) if event == "UserPromptSubmit" else on_tool(payload)
    if result:
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # fail closed: exit code 2 blocks the tool call in Claude Code
        sys.stderr.write(f"Harness-100 hook error, blocking for safety: {type(error).__name__}: {error}\n")
        sys.exit(2)
