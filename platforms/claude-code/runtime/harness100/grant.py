"""Explicit grants (v3.1-CC). See docs/GRANT-SPEC.md.

A grant is the ONLY source of an `allow` decision in the Claude Code hook.

Rule B (strict, round 2): a user message is a grant only when the WHOLE message (ignoring surrounding ASCII
spaces / newlines) is exactly one grant line:

    승인: 수정 src/**/*.py, tests/** · 실행 pytest · 기간 작업
    grant: edit docs/*.md; run npm test; scope session

- header exactly "승인: " or "grant: " (lower case, one ASCII space after the colon)
- no tab, no character that NFKC changes (full-width forms, NBSP, ideographic space ...), no format characters
- clause separators exactly " · ", "; " or " / " (ASCII spaces)
- a grant is bound to the working folder at the time it was given
Anything else is not a grant. Parsing never widens on doubt.

Rule A helper: normalize_command() strips git global options and maps "python -m pip" to "pip" so the hook can
classify risky actions on the command that will really run.
"""

import os
import re
import shlex
import unicodedata
from pathlib import Path

HEADERS = {"승인": {"edit": "수정", "run": "실행", "scope": "기간", "scopes": {"세션": "session", "작업": "task"}},
           "grant": {"edit": "edit", "run": "run", "scope": "scope", "scopes": {"session": "session", "task": "task"}}}
GRANT_LINE = re.compile(r"^(승인|grant): (\S(?:.*\S)?)$")
REVOKE_LINE = re.compile(r"^\s*(?:승인\s*취소|grant\s+revoke)\s*$", re.I)
TASK_END_LINE = re.compile(r"^\s*(?:작업\s*종료|task\s+end)\s*$", re.I)
CLAUSE_SPLIT = re.compile(r" · |; | / ")
CONTROL = re.compile(r"[;&|<>`\n\r]|\$\(")
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
MAX_GLOB_LEN = 200
MAX_GLOB_STARS = 12
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix",
                       "--config-env", "--attr-source"}
GIT_FLAG_OPTS = {"-P", "-p", "--no-pager", "--paginate", "--bare", "--literal-pathspecs", "--glob-pathspecs",
                 "--noglob-pathspecs", "--icase-pathspecs", "--no-replace-objects", "--no-optional-locks",
                 "--no-advice", "--html-path", "--man-path", "--info-path", "--version", "--help"}


def _strict_text(text):
    """Rule B character checks on the whole message."""
    if "\t" in text or unicodedata.normalize("NFKC", text) != text:
        return False
    return not any(unicodedata.category(ch) in ("Cf", "Zl", "Zp") or (unicodedata.category(ch) == "Zs" and ch != " ")
                   for ch in text)


def _valid_glob(pattern):
    p = pattern.strip(" ")
    if (not p or len(p) > MAX_GLOB_LEN or p.count("*") > MAX_GLOB_STARS or "***" in p or "\\" in p
            or p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/")):
        return None
    if not re.fullmatch(r"[\w.\-/*?@+=]+", p):
        return None  # path characters and * ? only: no spaces, quotes, shell or brace syntax
    return p


def parse_line(line):
    """Return a grant dict for one exact grant line, or None (no cwd attached)."""
    if not isinstance(line, str) or not _strict_text(line):
        return None
    m = GRANT_LINE.match(line)
    if not m:
        return None
    words_for = HEADERS[m.group(1)]
    clauses = CLAUSE_SPLIT.split(m.group(2))
    edit, run, scope = [], [], "session"
    for clause in clauses:
        key, sep, rest = clause.partition(" ")
        if not sep or not rest or rest != rest.strip(" ") or "  " in rest:
            return None  # "승인: 실행" (no scope), double spaces, trailing spaces -> not a grant
        if key == words_for["edit"]:
            globs = [_valid_glob(x) for x in rest.split(",")]
            if all(globs):
                edit.extend(globs)  # any invalid glob drops the whole clause (docs/GRANT-SPEC.md)
        elif key == words_for["run"]:
            if CONTROL.search(rest):
                return None
            try:
                prefix = shlex.split(rest)
            except ValueError:
                return None
            if not prefix:
                return None
            run.append(prefix)
        elif key == words_for["scope"]:
            if rest not in words_for["scopes"]:
                return None
            scope = words_for["scopes"][rest]
        else:
            return None  # unknown clause -> the whole line is not a grant
    if not edit and not run:
        return None
    return {"edit": edit, "run": run, "scope": scope}


def parse_prompt(text, cwd=None):
    """Return (grants, revoke, task_end, remaining_text).

    Rule B: the whole message must be exactly one grant line; otherwise it carries no grant (quoted, fenced or
    pasted grant lines are therefore ignored). Revoke / task-end lines only narrow and are honoured on any line.
    """
    text = text if isinstance(text, str) else ""
    whole = text.strip(" \n\r")
    grant = parse_line(whole) if "\n" not in whole and "\r" not in whole else None
    if grant:
        grant["cwd"] = str(cwd) if isinstance(cwd, str) and cwd else None
        return [grant], False, False, ""
    lines = text.replace("\r\n", "\n").split("\n")
    revoke = any(REVOKE_LINE.match(line) for line in lines)
    task_end = any(TASK_END_LINE.match(line) for line in lines)
    rest = "\n".join(line for line in lines if not REVOKE_LINE.match(line) and not TASK_END_LINE.match(line))
    return [], revoke, task_end, rest.strip()


def _glob_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.I if os.name == "nt" else 0)


def _relative_inside(root_dir, file_path):
    if not root_dir or not isinstance(file_path, str) or not file_path.strip() or "\x00" in file_path:
        return None
    if re.search(r":(?![\\/])", file_path[2:]):
        return None  # NTFS alternate data streams ("a.py::$DATA") and other colon forms are never matched
    try:
        root = Path(root_dir).resolve()
        path = Path(file_path)
        path = (path if path.is_absolute() else root / path).resolve()
        rel = path.relative_to(root)
    except (OSError, ValueError):
        return None
    rel = rel.as_posix()
    return None if rel in ("", ".") else rel


def edit_matches(grants, tool_input, cwd):
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    for grant in grants:
        root = grant.get("cwd") or cwd  # a grant is bound to the folder where it was given
        if grant.get("cwd") and cwd and Path(grant["cwd"]).resolve() != Path(cwd).resolve():
            continue  # the session moved to another folder: the grant does not follow it
        rel = _relative_inside(root, target)
        if rel is None:
            continue
        for pattern in grant.get("edit", []):
            if _glob_regex(pattern).match(rel):
                return f"수정 {pattern}"
    return None


def normalize_command(command):
    """(tokens, flags) for the command that will really run. flags: global_opts (git options that retarget the
    repository or config were present), config_override (git -c alias.*/core.* etc.)."""
    flags = {"global_opts": False, "config_override": False}
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None, flags
    if not tokens:
        return tokens, flags
    program = os.path.basename(tokens[0]).lower()
    if program in ("git", "git.exe"):
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            opt = tokens[i]
            name = opt.split("=", 1)[0]
            if name in GIT_OPTS_WITH_VALUE:
                flags["global_opts"] = True
                value = opt.split("=", 1)[1] if "=" in opt else (tokens[i + 1] if i + 1 < len(tokens) else "")
                if name in ("-c", "--config-env"):
                    flags["config_override"] = True
                i += 1 if "=" in opt else 2
            elif name in GIT_FLAG_OPTS:
                flags["global_opts"] = True
                i += 1
            else:
                flags["global_opts"] = True  # unknown leading option: treat as retargeting
                i += 1
        tokens = ["git"] + tokens[i:]
    elif program in ("python", "python3", "py", "python.exe") and tokens[1:3] == ["-m", "pip"]:
        tokens = ["pip"] + tokens[3:]
    return tokens, flags


def run_matches(grants, command):
    """All matching run clauses (normalized command), longest prefix first."""
    if not isinstance(command, str) or not command.strip() or CONTROL.search(command):
        return []
    tokens, _ = normalize_command(command)
    if not tokens:
        return []
    found = [prefix for grant in grants for prefix in grant.get("run", []) if tokens[:len(prefix)] == prefix]
    return ["실행 " + " ".join(prefix) for prefix in sorted(found, key=len, reverse=True)]


def matches(grants, tool, tool_input, cwd):
    """Every grant clause (str) that covers this tool call, most specific first. Pure function, no side effects."""
    if not grants or not isinstance(tool_input, dict):
        return []
    if tool in EDIT_TOOLS:
        clause = edit_matches(grants, tool_input, cwd)
        return [clause] if clause else []
    if tool in SHELL_TOOLS:
        return run_matches(grants, tool_input.get("command"))
    return []


def match(grants, tool, tool_input, cwd):
    """First (most specific) matching grant clause, or None."""
    found = matches(grants, tool, tool_input, cwd)
    return found[0] if found else None
