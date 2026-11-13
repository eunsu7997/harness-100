"""Record or compare SHA-256 hashes of pre-existing skills, settings and v3.0 originals.

Read-only: opens files for reading only, never writes inside the watched paths.
Usage:
  python -I -B tools/baseline.py record  <out.json>
  python -I -B tools/baseline.py compare <before.json> [<after.json>]
"""

import hashlib
import json
import os
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
DESKTOP_ORIGINAL = Path(__file__).resolve().parents[2]  # the v3.0 Claude-chat folder
CODEX_DAY = HOME / "Documents/Codex/2026-11-12"
SYNCED = HOME / ".claude/skills/synced/<UUID>_<UUID>"

FILES = [
    HOME / ".codex/AGENTS.md",
    HOME / ".claude/CLAUDE.md",
    HOME / ".agents/skills/prompt-builder-v2/SKILL.md",
    HOME / ".agents/skills/prompt-builder-v2/agents/openai.yaml",
    HOME / ".claude/skills/prompt-builder-v2/SKILL.md",
    HOME / ".claude/skills/harness-100/SKILL.md",
    HOME / ".codex/skills/prompt-builder/SKILL.md",
    HOME / ".codex/skills/prompt-builder/agents/openai.yaml",
    HOME / ".codex/plugins/cache/created-by-me-remote/basic-skill-v2/2.0.1/skills/prompt-builder-v2/SKILL.md",
    HOME / ".codex/config.toml",
    HOME / ".claude/settings.json",
    HOME / "Downloads/Harness-100-Universal-v3.0-Claude-Chat.zip",
    CODEX_DAY / "referenced-chatgpt-conversation-this-is-an-4/outputs/harness-100-universal-v3-mvp.zip",
]
TREES = [
    DESKTOP_ORIGINAL / "SKILL.md",
    DESKTOP_ORIGINAL / "references",
    CODEX_DAY / "referenced-chatgpt-conversation-this-is-an-4/outputs/harness-100-universal-v3-mvp",
    SYNCED / "harness-100-auto-router",
    SYNCED / "기본스킬",
    HOME / ".claude/skills/prompt-builder-v2",
]


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot():
    result = {}
    paths = list(FILES)
    for tree in TREES:
        if tree.is_file():
            paths.append(tree)
        elif tree.is_dir():
            paths.extend(sorted(p for p in tree.rglob("*") if p.is_file() and "__pycache__" not in p.parts))
        else:
            result[tree.as_posix()] = "absent"
    for path in paths:
        key = path.as_posix()
        try:
            result[key] = digest(path) if path.is_file() else "absent"
        except OSError as error:
            result[key] = f"unreadable:{type(error).__name__}"
    return result


def main(argv):
    if len(argv) >= 2 and argv[0] == "record":
        data = snapshot()
        Path(argv[1]).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"recorded": len(data), "absent": sum(v == "absent" for v in data.values())}))
        return 0
    if len(argv) >= 2 and argv[0] == "compare":
        before = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        after = json.loads(Path(argv[2]).read_text(encoding="utf-8")) if len(argv) > 2 else snapshot()
        changed = sorted(k for k in before if after.get(k) != before[k])
        added = sorted(k for k in after if k not in before)
        report = {"compared": len(before), "unchanged": len(before) - len(changed),
                  "changed": changed, "added": added, "result": "PASS" if not changed and not added else "FAIL"}
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["result"] == "PASS" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
