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

v3.2: a run grant allows exactly the granted command (token for token) in the work folder where it was given;
an edit grant matches the real path (checked by the hook first) with a linear-time glob matcher.
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


def raw_words(text):
    """v3.3 round 1: split on ASCII spaces only. Quotes and backslashes stay part of the words."""
    return [word for word in text.split(" ") if word] if isinstance(text, str) else []


def _strict_text(text):
    """Rule B character checks on the whole message."""
    if "\t" in text or unicodedata.normalize("NFKC", text) != text:
        return False
    return not any(unicodedata.category(ch) in ("Cf", "Zl", "Zp") or (unicodedata.category(ch) == "Zs" and ch != " ")
                   for ch in text)


def _valid_glob(pattern):
    p = pattern.strip(" ")
    if (not p or len(p) > MAX_GLOB_LEN or p.count("*") > MAX_GLOB_STARS or "***" in p or "\\" in p
            or p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/")
            or p.endswith("/") or "//" in p):  # v3.3 round 1: empty segments (`src/**/`) are not defined -> invalid
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
                shlex.split(rest)  # must still be a well-formed command
            except ValueError:
                return None
            prefix = raw_words(rest)  # v3.3 round 1: compared as raw text, never unquoted / unescaped
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


FIRST_LINE_MAX_LINES = 5
FIRST_LINE_MAX_CHARS = 400
PASTE_LINE = re.compile(
    r"^\s*(?:>|```|~~~|-{5,})|(?:승인|grant)\s*[:：]|[:：]\s*$|^\s*(?:from|to|cc|bcc|subject|date|sent|보낸\s*사람|받는\s*사람|제목)\s*[:：]|"
    r"\[(?:info|error|warn|warning|debug|trace|fatal)\]|^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|^\s*\d{1,2}:\d{2}", re.I)


def first_line_grant(text):
    """v3.3 fix 4. (grant, request) when the message's FIRST line is an exact grant line and the rest is a short,
    plain request; otherwise None. Pasted material that merely starts with a grant line is rejected by the request
    checks (length, blank lines, quotes/fences, other grant lines, ':'-ended preambles, mail/log headers)."""
    lines = text.replace("\r\n", "\n").split("\n")
    if len(lines) < 2 or "\r" in text.replace("\r\n", ""):
        return None
    grant = parse_line(lines[0].strip(" "))
    if not grant:
        return None
    rest_lines = lines[1:]
    while rest_lines and rest_lines[-1].strip(" ") == "":
        rest_lines.pop()  # trailing newline(s) at the end of the message
    rest = "\n".join(rest_lines)
    if not rest_lines or len(rest_lines) > FIRST_LINE_MAX_LINES or len(rest) > FIRST_LINE_MAX_CHARS:
        return None
    if any(not line.strip() or PASTE_LINE.search(line) for line in rest_lines):
        return None
    if any(REVOKE_LINE.match(line) or TASK_END_LINE.match(line) for line in rest_lines):
        return None  # v3.3 round 1: grant and revoke / task end in one message is ambiguous -> not a grant
    return grant, rest


def parse_prompt(text, cwd=None):
    """Return (grants, revoke, task_end, remaining_text).

    Rule B: the whole message must be exactly one grant line; otherwise it carries no grant (quoted, fenced or
    pasted grant lines are therefore ignored). Revoke / task-end lines only narrow and are honoured on any line.
    """
    text = text if isinstance(text, str) else ""
    whole = text.strip(" \n\r")
    grant = parse_line(whole) if "\n" not in whole and "\r" not in whole else None
    if grant:
        grant["cwd"] = os.path.realpath(cwd) if isinstance(cwd, str) and cwd else None  # unusable without a folder
        return [grant], False, False, ""
    first_line = first_line_grant(text)
    if first_line:
        grant, rest = first_line
        grant["cwd"] = os.path.realpath(cwd) if isinstance(cwd, str) and cwd else None
        rest_lines = rest.split("\n")
        return ([grant], any(REVOKE_LINE.match(line) for line in rest_lines),
                any(TASK_END_LINE.match(line) for line in rest_lines), rest.strip())
    lines = text.replace("\r\n", "\n").split("\n")
    revoke = any(REVOKE_LINE.match(line) for line in lines)
    task_end = any(TASK_END_LINE.match(line) for line in lines)
    rest = "\n".join(line for line in lines if not REVOKE_LINE.match(line) and not TASK_END_LINE.match(line))
    return [], revoke, task_end, rest.strip()


def _segment_match(pattern, text):
    """One path segment against * and ? (iterative two-pointer; no regex, no exponential backtracking)."""
    p = t = 0
    star, mark = -1, 0
    while t < len(text):
        if p < len(pattern) and (pattern[p] == "?" or pattern[p] == text[t]):
            p += 1
            t += 1
        elif p < len(pattern) and pattern[p] == "*":
            star, mark = p, t
            p += 1
        elif star != -1:
            p = star + 1
            mark += 1
            t = mark
        else:
            return False
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


def glob_match(pattern, rel):
    """v3.2: segment-wise dynamic programming. `**` as a whole segment matches zero or more segments; `*` and `?`
    never cross '/'. Time is bounded by len(segments) x len(path segments) x segment length."""
    fold = (lambda s: s.casefold()) if os.name == "nt" else (lambda s: s)
    ps = [fold(s) for s in pattern.split("/") if s]
    ts = [fold(s) for s in rel.split("/") if s]
    reach = [True] + [False] * len(ts)
    for index, seg in enumerate(ps):
        nxt = [False] * (len(ts) + 1)
        if seg == "**" and index == len(ps) - 1:
            # v3.3 decision 2: a trailing "**" covers the folder's contents only, never the folder itself
            for j in range(1, len(ts) + 1):
                nxt[j] = any(reach[:j])
        elif seg == "**":
            acc = False
            for j in range(len(ts) + 1):
                acc = acc or reach[j]
                nxt[j] = acc
        else:
            seg = re.sub(r"\*+", "*", seg)
            for j in range(1, len(ts) + 1):
                if reach[j - 1] and _segment_match(seg, ts[j - 1]):
                    nxt[j] = True
        reach = nxt
    return reach[len(ts)]


def _same_folder(a, b):
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError, TypeError):
        return False


def edit_matches(grants, target_real, cwd):
    """target_real: the real absolute path already checked by the hook (protected / ambiguous paths never get here).
    A grant applies only in the work folder where it was given."""
    if not isinstance(target_real, str) or not target_real:
        return None
    for grant in grants:
        root = grant.get("cwd")
        if not root or not _same_folder(root, cwd):
            continue
        try:
            rel = os.path.relpath(target_real, os.path.realpath(root))
        except ValueError:
            continue
        rel = rel.replace("\\", "/")
        if rel == "." or rel.startswith("../") or rel == ".." or os.path.isabs(rel):
            continue
        for pattern in grant.get("edit", []):
            if glob_match(pattern, rel):
                return f"수정 {pattern}"
    return None


def folder_itself(grants, target_real, cwd):
    """v3.3 decision 2: the `dir/**` clause whose folder `dir` IS the write target (a write there is denied)."""
    if not isinstance(target_real, str) or not target_real:
        return None
    for grant in grants:
        root = grant.get("cwd")
        if not root or not _same_folder(root, cwd):
            continue
        try:
            rel = os.path.relpath(target_real, os.path.realpath(root)).replace("\\", "/")
        except ValueError:
            continue
        for pattern in grant.get("edit", []):
            if pattern.endswith("/**") and glob_match(pattern[:-3], rel):
                return f"수정 {pattern}"
    return None


def command_tokens(command):
    if not isinstance(command, str) or not command.strip() or CONTROL.search(command):
        return None
    try:
        return shlex.split(command)
    except ValueError:
        return None


POWERSHELL_PLAIN = re.compile(r"[\w .=/:,@+\-]+")


def run_matches(grants, command, cwd, tool="Bash"):
    """v3.2: exact (work folder, full command) match. No prefix matching.

    v3.3 round 1: both sides are compared as raw text split on ASCII spaces only (only the number of spaces is
    ignored). Quotes and backslashes are never removed, so `"pytest" -q` or `p\\ytest -q` differ from `pytest -q`.
    Bash commands must still pass the shell-control check; PowerShell commands must be plain (letters, digits,
    spaces and . = / : , @ + -)."""
    if not isinstance(command, str):
        return None
    if tool == "PowerShell":
        if not POWERSHELL_PLAIN.fullmatch(command.strip(" ") or "\\"):
            return None
    elif command_tokens(command) is None:
        return None
    tokens = raw_words(command)
    if not tokens:
        return None
    for grant in grants:
        root = grant.get("cwd")
        if not root or not _same_folder(root, cwd):
            continue
        for granted in grant.get("run", []):
            if any(q in part for part in granted + tokens for q in "'\""):
                # v3.3 round 2: spaces inside quotes are data -> with a quote anywhere only the exact text matches
                if command.strip(" ") == " ".join(granted):
                    return "실행 " + " ".join(granted)
                continue
            if tokens == granted:
                return "실행 " + " ".join(granted)
    return None


def matches(grants, tool, tool_input, cwd, target_real=None):
    """Every grant clause (str) that covers this tool call. Pure function, no side effects."""
    if not grants or not isinstance(tool_input, dict):
        return []
    if tool in EDIT_TOOLS:
        clause = edit_matches(grants, target_real, cwd)
    elif tool in SHELL_TOOLS:
        clause = run_matches(grants, tool_input.get("command"), cwd, tool)
    else:
        clause = None
    return [clause] if clause else []


def match(grants, tool, tool_input, cwd, target_real=None):
    found = matches(grants, tool, tool_input, cwd, target_real)
    return found[0] if found else None
