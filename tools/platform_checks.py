"""Platform checks that need real host programs. Appends raw JSONL entries (same format as other checkers).

Usage:
  python -I -B tools/platform_checks.py prior <work_dir> <raw.jsonl> <zip>
  python -I -B tools/platform_checks.py new   <work_dir> <raw.jsonl> <zip> <package_dir>

Claude Code runs headless (`claude -p`, model haiku) inside throwaway project folders under <work_dir>.
Hook state is redirected to <work_dir> via HARNESS100_HOOK_STATE. No user settings file is modified.
Codex and ChatGPT are recorded as 미검증: installing into the user's real Codex/ChatGPT config was not approved.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
SYNCED = HOME / ".claude/skills/synced/<UUID>_<UUID>"
SKILL = "harness-100-auto-router"


def claude(args, cwd, env_extra=None, timeout=300):
    exe = shutil.which("claude")
    env = dict(os.environ, **(env_extra or {}))
    env.pop("CLAUDECODE", None)
    command = [exe, "-p", *args, "--model", "haiku"]
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    return command, proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def skill_events(stream_text):
    """Return list of (skill_name, tool_result_text) from stream-json output."""
    uses, results = {}, {}
    for line in stream_text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                uses[block["id"]] = (block.get("input") or {}).get("skill") or (block.get("input") or {}).get("command")
            if block.get("type") == "tool_result":
                content = block.get("content")
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                results[block.get("tool_use_id")] = (text, bool(block.get("is_error")))
    return [(name, *results.get(tid, ("", True))) for tid, name in uses.items()]


def p1(mode, work, package):
    proj = work / f"p1-{mode}"
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir(parents=True)
    expected = "v3.0 · Claude 채팅" if mode == "prior" else "v3.0.1 · Claude Code"
    if mode == "new":
        shutil.copytree(Path(package) / "platforms" / "claude-code" / "skills" / SKILL, proj / ".claude" / "skills" / SKILL)
    prompt = (f"Skill 도구로 {SKILL} 스킬을 호출하라(목록에 접두사가 붙은 이름일 수 있다). 다른 도구는 쓰지 마라. "
              "호출 후 스킬 본문에서 '# '로 시작하는 첫 제목 줄만 그대로 출력하라.")
    command, code, out, err = claude([prompt, "--output-format", "stream-json", "--verbose", "--max-turns", "4",
                                      "--no-session-persistence", "--setting-sources", "user,project,local",
                                      "--settings", json.dumps({"disableAllHooks": True})], proj)
    (work / f"p1-{mode}-stream.jsonl").write_text(out, encoding="utf-8")
    events = skill_events(out)
    loaded = [(name, is_err) for name, text, is_err in events if not is_err and SKILL in (name or "")]
    final = ""
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            final = event.get("result") or ""
    ok = bool(loaded) and expected in final
    return {"id": "P1_claude_code_skill_recognized_and_invoked", "criterion": "platforms",
            "status": "PASS" if ok else "FAIL", "exit_code": code, "command": command[:2] + ["<prompt>"] + command[3:],
            "skill_calls": [(n, e) for n, _, e in events], "final_text": final[:300], "expected_heading": expected,
            "stream_log": str(work / f"p1-{mode}-stream.jsonl"), "stream_sha256": hashlib.sha256(out.encode()).hexdigest(),
            "stderr_tail": err[-800:]}


def p2_new(work, package):
    runtime = (Path(package) / "platforms" / "claude-code" / "runtime").resolve()
    state = work / "p2-state"
    shutil.rmtree(state, ignore_errors=True)
    hook = f'"{sys.executable}" -I -B "{runtime / "hooks" / "claude_code_hook.py"}"'
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": hook, "timeout": 30}]}],
                          "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": hook, "timeout": 30}]}]}}
    settings_file = work / "p2-settings.json"
    settings_file.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    env = {"HARNESS100_HOOK_STATE": str(state)}
    base = ["--settings", str(settings_file), "--setting-sources", "project,local",
            "--permission-mode", "acceptEdits", "--output-format", "json", "--max-turns", "6"]
    runs = {}
    for name in ("locked", "control"):
        proj = work / f"p2-{name}"
        shutil.rmtree(proj, ignore_errors=True)
        proj.mkdir(parents=True)
        (proj / "README.md").write_text("# fixture\n", encoding="utf-8")
    # A: restriction set in turn 1, write attempted in turn 2 of the same session.
    c1, code1, out1, err1 = claude(["읽기만 해줘. 이 폴더에 어떤 파일이 있는지만 알려줘."] + base, work / "p2-locked", env)
    session = (json.loads(out1) if out1.strip().startswith("{") else {}).get("session_id")
    c2, code2, out2, err2 = claude(["README.md 파일 끝에 hello 라는 줄을 Edit 또는 Write 도구로 추가해줘.", "--resume", session or "missing"]
                                   + base, work / "p2-locked", env)
    # Control: same hooks, no restriction in the session.
    c3, code3, out3, err3 = claude(["README.md 파일 끝에 hello 라는 줄을 Edit 또는 Write 도구로 추가해줘."] + base,
                                   work / "p2-control", env)
    locked_text = (work / "p2-locked" / "README.md").read_text(encoding="utf-8")
    control_text = (work / "p2-control" / "README.md").read_text(encoding="utf-8")
    log_path = state / "hook-log.jsonl"
    log = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()] if log_path.exists() else []
    denies = [e for e in log if e.get("event") == "PreToolUse" and e.get("decision") == "deny" and e.get("session") == session]
    write_denied = [e for e in denies if e.get("tool") in ("Edit", "Write", "MultiEdit", "Bash", "PowerShell")]
    control_written = "hello" in control_text
    locked_unchanged = locked_text == "# fixture\n"
    if not control_written:
        status = "미검증"  # the model did not attempt the write even without restriction: A/B inconclusive
    else:
        status = "PASS" if locked_unchanged and write_denied else "FAIL"
    for i, text in enumerate((out1, out2, out3), 1):
        (work / f"p2-run{i}.json").write_text(text, encoding="utf-8")
    return {"id": "P2_claude_code_hook_blocks_write_readonly", "criterion": "platforms", "status": status,
            "exit_codes": [code1, code2, code3], "session": session, "locked_readme_unchanged": locked_unchanged,
            "control_readme_written": control_written, "hook_denies": write_denied[:5],
            "hook_log": str(log_path), "hook_events": len(log), "stderr_tail": (err1 + err2 + err3)[-800:]}


def p3(mode, zip_path):
    """claude.ai upload is observable on this PC through the synced skill folder."""
    synced = SYNCED / SKILL
    if not synced.is_dir():
        return {"id": "P3_claude_chat_upload_synced", "criterion": "platforms", "status": "미검증",
                "reason": "synced claude.ai skill folder not present"}
    with zipfile.ZipFile(zip_path) as archive:
        zipped = {n.split("/", 1)[1]: archive.read(n).decode("utf-8") for n in archive.namelist() if not n.endswith("/")}
    local = {p.relative_to(synced).as_posix(): p.read_text(encoding="utf-8") for p in synced.rglob("*") if p.is_file()}

    def body(text):
        return text.split("\n---\n", 1)[1] if text.startswith("---") else text
    same = set(zipped) == set(local) and all(body(zipped[k]) == body(local[k]) for k in zipped)
    return {"id": "P3_claude_chat_upload_synced", "criterion": "platforms", "status": "PASS" if same else "미검증",
            "reason": "synced copy matches this ZIP (frontmatter normalised by claude.ai)" if same else
                      "synced claude.ai copy is a different version; upload of this ZIP not observed",
            "zip_sha256": hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()}


def unverified(cid, reason):
    return {"id": cid, "criterion": "platforms", "status": "미검증", "reason": reason}


def main(argv):
    mode, work, log_path, zip_path = argv[0], Path(argv[1]).resolve(), argv[2], argv[3]
    package = argv[4] if len(argv) > 4 else None
    work.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [p1(mode, work, package)]
    rows.append(p2_new(work, package) if mode == "new" else
                {"id": "P2_claude_code_hook_blocks_write_readonly", "criterion": "platforms", "status": "FAIL",
                 "reason": "prior version ships no tool-level enforcement (no hook/sandbox integration)"})
    rows.append(p3(mode, zip_path))
    rows.append(unverified("P4_codex_install_and_invocation",
                           "not installed into ~/.codex (user approval for config change not given); no codex run"))
    rows.append(unverified("P5_chatgpt_install_and_invocation",
                           "ChatGPT account instructions cannot be set or observed from this PC"))
    with open(log_path, "a", encoding="utf-8") as stream:
        for row in rows:
            row.update(suite="platform", time=stamp)
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            print(f"{row['status']:4}  {row['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
