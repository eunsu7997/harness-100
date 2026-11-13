import hashlib
import os
import re
import sys
import unittest
import zipfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HOME = Path(os.path.expanduser("~"))
SKILL = "harness-100-auto-router"
ZIP = PKG / "dist" / "Harness-100-Universal-v3.1-cc-Claude-Chat.zip"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frontmatter(text):
    assert text.startswith("---\n"), "missing frontmatter"
    header = text[4:].split("\n---\n", 1)[0]
    data = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


@unittest.skipUnless((PKG / "platforms").is_dir(), "run tools/build.py first")
class Package(unittest.TestCase):
    def skill_dirs(self):
        return [PKG / "platforms" / "claude-chat" / SKILL, PKG / "platforms" / "claude-code" / "skills" / SKILL,
                PKG / "platforms" / "codex" / "skills" / SKILL]

    def test_every_platform_carries_the_identical_core(self):
        core = {p.relative_to(PKG / "core").as_posix(): sha(p) for p in (PKG / "core").rglob("*.md")}
        for folder in self.skill_dirs():
            with self.subTest(folder=folder.parent.name):
                refs = {p.relative_to(folder / "references").as_posix(): sha(p) for p in (folder / "references").rglob("*.md")}
                self.assertEqual(core, refs)
        chat = {p.relative_to(PKG / "platforms" / "chatgpt").as_posix(): sha(p)
                for p in (PKG / "platforms" / "chatgpt").rglob("*.md") if "instructions" not in p.name}
        self.assertEqual(core, chat)

    def test_skill_metadata(self):
        for folder in self.skill_dirs():
            meta = frontmatter((folder / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(meta["name"], SKILL)
            self.assertRegex(meta["name"], r"^[a-z0-9-]{1,64}$")
            self.assertTrue(0 < len(meta["description"]) <= 200, len(meta["description"]))
            self.assertIn("프롬프트 작성은 제외", meta["description"])

    def test_zip_structure_and_links(self):
        with zipfile.ZipFile(ZIP) as archive:
            self.assertIsNone(archive.testzip())
            names = [n for n in archive.namelist() if not n.endswith("/")]
            self.assertEqual({n.split("/")[0] for n in names}, {SKILL})
            self.assertFalse([n for n in names if ".." in n.split("/") or "\\" in n])
            files = {n: archive.read(n).decode("utf-8") for n in names}
        for name, text in files.items():
            for target in re.findall(r"\]\(([^)#\s]+)", text):
                resolved = os.path.normpath(os.path.join(os.path.dirname(name), target)).replace("\\", "/")
                self.assertIn(resolved, files, f"{name} -> {target}")
        self.assertIn("v3.1-cc", files[f"{SKILL}/SKILL.md"])

    def test_coexistence_with_basic_skill(self):
        for folder in self.skill_dirs():
            body = (folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("/기본스킬", body, "must not claim the basic-skill alias")
            self.assertTrue("중복" in body or "한 번만" in body, "must state the prompt is produced once")
        basic = HOME / ".claude" / "skills" / "prompt-builder-v2" / "SKILL.md"
        if basic.exists():
            self.assertEqual(frontmatter(basic.read_text(encoding="utf-8-sig"))["name"], "prompt-builder-v2")

    def test_no_local_name_conflict(self):
        """A *local* skill with the same name would double-trigger. The claude.ai synced copy is the
        previous version of this same skill (to be replaced by upload) and is reported, not failed."""
        ours = {sha(p / "SKILL.md") for p in self.skill_dirs()}
        local_roots = [HOME / ".claude" / "skills", HOME / ".codex" / "skills", HOME / ".agents" / "skills"]
        # An installed copy of THIS package (same SKILL.md) is our own install, not a conflict.
        # v3.1-cc: an installed *previous version* of this same package (its SKILL.md is a Harness-100 skill) is the
        # same skill awaiting replacement, like the synced copy: reported, not failed. A different skill that
        # reuses the name is a conflict.
        def previous_version(folder):
            path = folder / "SKILL.md"
            return path.exists() and "Harness-100" in path.read_text(encoding="utf-8", errors="replace")
        conflicts = [str(r / SKILL) for r in local_roots
                     if (r / SKILL).exists() and not ((r / SKILL / "SKILL.md").exists() and sha(r / SKILL / "SKILL.md") in ours)
                     and not previous_version(r / SKILL)]
        self.assertEqual(conflicts, [])

    def test_chatgpt_short_fits_custom_instruction_limit(self):
        self.assertLessEqual(len((PKG / "platforms" / "chatgpt" / "instructions-short.md").read_text(encoding="utf-8")), 1500)

    def test_runtime_copies_match_source(self):
        for platform in ("claude-code", "codex"):
            runtime = PKG / "platforms" / platform / "runtime"
            for src in list((PKG / "harness100").glob("*.py")) + list((PKG / "hooks").glob("*.py")):
                with self.subTest(platform=platform, file=src.name):
                    self.assertEqual(sha(src), sha(runtime / src.parent.name / src.name))


if __name__ == "__main__":
    unittest.main()
