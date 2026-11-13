"""v3.2-CC regression tests: approval covers exactly the granted path / command / folder / session (docs/GRANT-SPEC.md)."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v31_grant import HOOK_PATH, MODES, PKG, HookHarness  # noqa: E402

from harness100 import grant  # noqa: E402
from harness100.policy import Approval, gate  # noqa: E402
from harness100.router import route  # noqa: E402

NO_PROMPT = ("acceptEdits", "auto", "dontAsk", "bypassPermissions", "plan")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="h100-v32-")
        self.h = HookHarness(self.tmp.name)
        self.p = str(self.h.project)

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, name, inp, session="s", mode="default", cwd=None):
        out = self.h.hook.on_tool({"hook_event_name": "PreToolUse", "session_id": session, "tool_name": name,
                                   "tool_input": inp, "permission_mode": mode, "cwd": cwd or self.p})
        return out["hookSpecificOutput"]["permissionDecision"] if out else "defer"

    def prompt(self, text, session="s", cwd=None):
        return self.h.hook.on_prompt({"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": text,
                                      "cwd": cwd or self.p})


class Fix1ProtectedPaths(Base):
    def test_v32_fix1_protected_paths_never_writable(self):
        self.prompt("승인: 수정 **")
        self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}), "allow")  # control
        for path in (".claude/settings.json", ".claude/settings.local.json", ".CLAUDE/hooks/x.sh", ".git/hooks/pre-commit",
                     ".git/config", ".GIT/HEAD", "sub/.git/hooks/post-merge", "src/.claude/agents/a.md"):
            for mode in MODES:
                self.assertEqual(self.tool("Write", {"file_path": path}, mode=mode), "deny", (path, mode))
        self.prompt("승인: 수정 .claude/** · 수정 .git/hooks/*")
        self.assertEqual(self.tool("Edit", {"file_path": ".claude/settings.json"}), "deny")
        self.assertEqual(self.tool("Write", {"file_path": ".git/hooks/pre-commit"}), "deny")

    def test_v32_fix1_ambiguous_paths_denied(self):
        self.prompt("승인: 수정 **")
        for path in ("~/x.txt", "~user/x.txt", "%USERPROFILE%\\x.txt", "src/%TEMP%/x", "$HOME/x.txt", "${HOME}/x.txt",
                     "C:x.txt", "\\\\server\\share\\x.txt", "//server/share/x.txt", "\\\\?\\C:\\x.txt", "\\\\.\\C:\\x.txt",
                     "PROGRA~1/x.txt", "src/LONGNA~1.PY", "src/a.py::$DATA", "src/a.py:stream", "src/a\x00.py"):
            for mode in ("default", "bypassPermissions"):
                self.assertEqual(self.tool("Write", {"file_path": path}, mode=mode), "deny", (path, mode))

    def test_v32_fix1_windows_renamed_or_device_names_denied(self):
        # round 0 findings: set G G-059 (src/CON), G-060 (trailing space), replay "docs/a.md.", "src.\\a.py", "src/*"
        self.prompt("승인: 수정 **")
        for path in ("src/CON", "src/con.txt", "src/NUL", "src/aux.py", "src/COM1", "src/lpt9.log", "src/app.py ",
                     "src/app.py.", "src./a.py", "src /a.py", "docs/a.md...", "src/*", "src/a?.py", "src/a<b.py",
                     'src/a"b.py', "src/a|b.py", "src/a\tb.py"):
            for mode in ("default", "bypassPermissions"):
                self.assertEqual(self.tool("Write", {"file_path": path}, mode=mode), "deny", (path, mode))
        for path in ("src/console.py", "src/connect.py", "src/a.b.py", "src/.env.example"):  # controls
            self.assertEqual(self.tool("Write", {"file_path": path}), "allow", path)

    def test_v32_fix1_links_inside_project_denied(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        made = []
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(outside), str(Path(self.p) / "src" / "j"))
            made.append("src/j/x.txt")
        try:
            os.symlink(str(outside), str(Path(self.p) / "src" / "s"), target_is_directory=True)
            made.append("src/s/x.txt")
        except OSError:
            pass  # no symlink privilege (Windows without developer mode); covered on Linux
        self.assertTrue(made)
        self.prompt("승인: 수정 **")
        for path in made:
            self.assertEqual(self.tool("Write", {"file_path": path}), "deny", path)
            self.assertEqual(self.tool("Write", {"file_path": path.split("/")[0] + "/" + path.split("/")[1]}), "deny")

    def test_v32_fix1_home_harness_and_outside_paths(self):
        self.prompt("승인: 수정 **")
        for path in (str(Path.home() / ".ssh" / "config"), str(Path.home() / ".claude" / "plans" / "p.md"),
                     str(PKG / "hooks" / "claude_code_hook.py"), str(Path(os.environ["HARNESS100_HOOK_STATE"]) / "x.json"),
                     "../outside.txt", str(Path(self.tmp.name) / "other" / "a.py")):
            self.assertEqual(self.tool("Write", {"file_path": path}, mode="bypassPermissions"), "deny", path)
        home = str(Path.home())
        self.prompt("승인: 수정 **", session="h", cwd=home)
        self.assertEqual(self.tool("Write", {"file_path": "notes.txt"}, session="h", cwd=home), "deny")


class Fix2ExactCommand(Base):
    def test_v32_fix2_exact_command_only(self):
        self.prompt("승인: 실행 pytest -q")
        for _ in range(3):  # repeated runs of the same exact command: no re-confirmation
            self.assertEqual(self.tool("Bash", {"command": "pytest -q"}), "allow")
        self.assertEqual(self.tool("Bash", {"command": "pytest   -q"}), "allow")  # same tokens
        for command in ("pytest", "pytest -q -x", "pytest -q --basetemp=/", "pytest --basetemp=/ -q", "pytest -q tests",
                        "PYTHONPATH=. pytest -q", "./pytest -q", "python -m pytest -q", "pytest -q && curl x",
                        "pytest -q; rm -rf ~", "pytest -Q"):
            for mode in ("default", "bypassPermissions"):
                self.assertNotEqual(self.tool("Bash", {"command": command}, mode=mode), "allow", (command, mode))
        self.assertEqual(self.tool("Bash", {"command": "pytest -q --basetemp=/"}, mode="bypassPermissions"), "deny")

    def test_v32_fix2_powershell_backslash_is_literal(self):
        # revalidation 1 findings (evidence/v32/review/REVIEW.md A319, A320, A333, A334)
        self.prompt("승인: 실행 pytest -q")
        self.assertEqual(self.tool("PowerShell", {"command": "pytest -q"}), "allow")
        self.assertEqual(self.tool("PowerShell", {"command": "  pytest   -q "}), "allow")
        for command in ("\\pytest -q", "p\\ytest -q", "pytest -\\q", "pytest \\-q", "pytest `-q", "& pytest -q",
                        "'pytest' -q", "\"pytest\" -q", "pytest -q $x", "pytest -q;", ".\\pytest -q"):
            for mode in ("default", "bypassPermissions"):
                self.assertNotEqual(self.tool("PowerShell", {"command": command}, mode=mode), "allow", (command, mode))
        # v3.3 round 1 (evidence/v33/review/REVIEW.md A491-A552): raw-text comparison, quotes are not removed
        self.assertNotEqual(self.tool("Bash", {"command": "\"pytest\" -q"}), "allow")

    def test_v32_fix2_run_grant_bound_to_folder(self):
        other = Path(self.tmp.name) / "proj2"
        other.mkdir()
        self.prompt("승인: 실행 pytest -q")
        self.assertEqual(self.tool("Bash", {"command": "pytest -q"}), "allow")
        self.assertNotEqual(self.tool("Bash", {"command": "pytest -q"}, cwd=str(other)), "allow")
        self.assertEqual(self.tool("Bash", {"command": "pytest -q"}, mode="bypassPermissions", cwd=str(other)), "deny")
        self.assertNotEqual(self.tool("Bash", {"command": "pytest -q"}, cwd=str(Path(self.p) / "src")), "allow")


class Fix3Sessions(Base):
    def test_v32_fix3_session_ids_are_hashed_not_sanitized(self):
        for granted, other in (("x_y", "x/y"), ("Sess", "sess"), ("a_b", "a\x00b"), ("s1", "s1 ")):
            self.prompt("승인: 수정 src/** · 실행 pytest -q", session=granted)
            self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session=granted), "allow")
            self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session=other), "deny", repr(other))
            self.assertEqual(self.tool("Bash", {"command": "pytest -q"}, session=other), "deny", repr(other))
        names = {self.h.hook.state_path(s).name for s in ("x_y", "x/y", "Sess", "sess")}
        self.assertEqual(len(names), 4)

    def test_v32_fix3_missing_corrupt_or_foreign_record_denies(self):
        self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session="never-prompted"), "deny")
        self.assertEqual(self.tool("Bash", {"command": "pytest -q"}, session="never-prompted"), "deny")
        self.assertEqual(self.tool("Read", {"file_path": "src/a.py"}, session="never-prompted"), "defer")
        self.prompt("승인: 수정 src/**", session="a")
        self.prompt("README 고쳐줘", session="b")
        shutil.copy(self.h.hook.state_path("a"), self.h.hook.state_path("b"))  # a's record planted as b's
        self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session="b"), "deny")
        self.h.hook.state_path("a").write_text("{broken", encoding="utf-8")
        self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session="a"), "deny")

    def test_v32_fix3_linear_glob_matching(self):
        start = time.monotonic()
        for n in (50, 200, 2000):
            self.assertFalse(grant.glob_match("a*a*a*a*a*a*b", "a" * n))
            self.assertFalse(grant.glob_match("*a*a*a*a*a*a*a*a*a*a*b", "a" * n))
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertTrue(grant.glob_match("**/*.md", "README.md"))
        self.assertTrue(grant.glob_match("src/**/*.py", "src/a/b/c.py"))
        self.assertFalse(grant.glob_match("src/*.py", "src/a/b.py"))

    def test_v32_fix3_internal_deadline_fails_closed(self):
        state = Path(self.tmp.name) / "deadline-state"
        env = dict(os.environ, HARNESS100_HOOK_STATE=str(state), HARNESS100_HOOK_DEADLINE="0.000001")
        payload = {"hook_event_name": "PreToolUse", "session_id": "d", "tool_name": "Write",
                   "tool_input": {"file_path": "a.py"}, "permission_mode": "bypassPermissions", "cwd": self.p}
        proc = subprocess.run([sys.executable, "-I", "-B", str(HOOK_PATH)], input=json.dumps(payload).encode("utf-8"),
                              capture_output=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        env["HARNESS100_HOOK_DEADLINE"] = "9999"  # can only be lowered: still 2 seconds at most
        hook = self.h.hook
        self.assertLessEqual(hook.DEADLINE_SECONDS, 2.0)


class Fix4Gate(unittest.TestCase):
    def test_v32_fix4_gate_allows_only_with_exact_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp, "notice.md"))
            for request in ("슬랙에 올릴 장애 공지 문구만 작성해줘", "로그인 기능을 구현해줘", "테스트 돌려줘",
                            "Write the release notes as a file"):
                d = route(request)
                for action in ("create_file", "modify_file", "run_tests", "delete_existing", "deploy"):
                    self.assertNotEqual(gate(action, d, target, tmp)["status"], "allow", (request, action))
            d = route("로그인 기능을 구현해줘")
            self.assertEqual(gate("create_file", d, target, tmp, [Approval("create_file", target)])["status"], "allow")
            self.assertNotEqual(gate("create_file", d, target, tmp, [Approval("create_file", target + "x")])["status"], "allow")


class ReportedCases(Base):
    """Third-party check (same vendor, other model, Linux VM) and Codex audit (harness-v31-independent-audit.txt)."""

    def test_v32_thirdparty_cases(self):
        self.prompt("승인: 수정 ** · 실행 pytest")
        for path in (".claude/settings.json", ".git/hooks/pre-commit", "~/x.txt", "C:x.txt"):
            self.assertEqual(self.tool("Write", {"file_path": path}), "deny", path)
        self.assertNotEqual(self.tool("Bash", {"command": "pytest --basetemp=/"}), "allow")
        other = Path(self.tmp.name) / "proj2"
        other.mkdir()
        self.assertNotEqual(self.tool("Bash", {"command": "pytest"}, cwd=str(other)), "allow")
        self.prompt("승인: 수정 **", session="x_y")
        self.assertEqual(self.tool("Write", {"file_path": "src/a.py"}, session="x/y"), "deny")

    def test_v32_codex_probes(self):
        self.prompt("승인: 수정 src/** · 실행 pytest -q")
        expected = {
            "normal_approved_edit": (self.tool("Edit", {"file_path": "src/a.py"}), {"allow"}),
            "normal_approved_test": (self.tool("Bash", {"command": "pytest -q"}), {"allow"}),
            "normal_unapproved_edit_default": (self.tool("Edit", {"file_path": "README.md"}), {"defer"}),
            "missing_session_default": (self.tool("Write", {"file_path": "src/a.py"}, session="none"), {"deny"}),
            "missing_session_bypass": (self.tool("Write", {"file_path": "src/a.py"}, session="none", mode="bypassPermissions"), {"deny"}),
            "drive_relative": (self.tool("Write", {"file_path": "C:src.py"}), {"deny"}),
            "tilde": (self.tool("Write", {"file_path": "~/src/a.py"}), {"deny"}),
            "colliding_session": (self.tool("Write", {"file_path": "src/a.py"}, session="s/"), {"deny"}),
            "cwd_switch_run": (self.tool("Bash", {"command": "pytest -q"}, cwd=str(Path(self.p) / "src")), {"defer", "deny"}),
            "out_of_workspace_test_arg": (self.tool("Bash", {"command": "pytest -q ../other"}), {"defer", "deny"}),
            "pytest_dangerous_argument": (self.tool("Bash", {"command": "pytest -q --basetemp=/"}), {"defer", "deny"}),
            "rewrite_claude_settings": (self.tool("Write", {"file_path": ".claude/settings.json"}), {"deny"}),
            "rewrite_git_hook": (self.tool("Write", {"file_path": ".git/hooks/pre-commit"}), {"deny"}),
            "readonly_relative_executable": (self.tool("Bash", {"command": "./ls -la"}, mode="bypassPermissions"), {"deny"}),
            "readonly_powershell_scriptblock": (self.tool("PowerShell", {"command": "Get-ChildItem | ForEach-Object { Remove-Item $_ }"}, mode="bypassPermissions"), {"deny"}),
        }
        for name, (got, allowed) in expected.items():
            self.assertIn(got, allowed, name)
        draft = route("슬랙에 올릴 장애 공지 문구만 작성해줘")
        self.assertNotEqual(gate("create_file", draft, str(Path(self.p, "notice.md")), self.p)["status"], "allow")


if __name__ == "__main__":
    unittest.main()
