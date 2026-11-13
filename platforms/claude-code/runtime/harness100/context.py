"""Bounded read-only observations. Project text never grants authority.

No project program, hook, filter or test is executed here; Git is observed via safe_git."""

import hashlib
import json
import os
from pathlib import Path
from . import safe_git


SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
DOCUMENTS = {"AGENTS.md", "CLAUDE.md", "SKILL.md", "README.md", "package.json", "pyproject.toml", "pytest.ini"}
RISK_TERMS = ("auth", "payment", "secret", "credential", "migration", "security", "permission")


def sensitive_path(name):
    return any(term in name.casefold() for term in RISK_TERMS)


def git_changes(root, trace_file=None):
    """Observe Git changes without letting the repository run code (see safe_git)."""
    return safe_git.status(root, trace_file=trace_file)


def inspect_project(project):
    root = Path(project).resolve()
    observation = {"status": "unknown", "root": str(root), "files": [], "read_files": [],
                   "test_files": [], "test_commands": [], "risk_files": [], "unknowns": [],
                   "git": {"status": "unknown", "changes": []}}
    if not root.is_dir():
        observation["unknowns"].append("Project directory missing or inaccessible")
        return observation
    errors = []
    paths = []
    truncated = False
    # Avoid linked directories and NTFS junctions when collecting project context.
    for folder, directories, filenames in os.walk(root, onerror=lambda error: errors.append(type(error).__name__)):
        directories[:] = sorted(name for name in directories if name not in SKIP
                                and not Path(folder, name).is_symlink()
                                and not Path(folder, name).is_junction())
        if len(Path(folder).relative_to(root).parts) >= 6:
            truncated = truncated or bool(directories)
            directories[:] = []
        for name in sorted(filenames):
            path = Path(folder, name)
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            paths.append(path)
            if len(paths) >= 500:
                truncated = True
                break
        if len(paths) >= 500:
            break
    for path in paths:
        relative = path.relative_to(root).as_posix()
        observation["files"].append(relative)
        if sensitive_path(relative):
            observation["risk_files"].append(relative)
        if path.name.startswith("test_") or path.name.endswith((".test.ts", ".test.js", ".spec.ts", "_test.py")):
            observation["test_files"].append(relative)
        if path.name not in DOCUMENTS:
            continue
        try:
            with path.open("rb") as stream:
                data = stream.read(65537)
            if len(data) > 65536:
                observation["unknowns"].append(f"File too large to inspect: {relative}")
                continue
            observation["read_files"].append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
            if path.name == "package.json":
                manifest = json.loads(data.decode("utf-8-sig"))
                scripts = manifest.get("scripts", {})
                if isinstance(scripts, dict):
                    observation["test_commands"].extend("npm run " + key for key in scripts if key == "test" or key.startswith("test:"))
        except (OSError, UnicodeError, ValueError, AttributeError) as error:
            observation["unknowns"].append(f"Unreadable {relative}: {type(error).__name__}")
    observation["git"] = git_changes(root)
    changed_risks = [item["path"] for item in observation["git"]["changes"] if sensitive_path(item["path"])]
    observation["risk_files"] = sorted(set(observation["risk_files"] + changed_risks))
    incomplete = errors or truncated or observation["unknowns"] or observation["git"]["status"] == "unknown"
    observation["status"] = "partial" if incomplete else "observed"
    observation["unknowns"].extend(errors)
    if truncated:
        observation["unknowns"].append("Project scan limited to 500 files and depth 6")
    if observation["git"]["status"] == "unknown":
        observation["unknowns"].append(observation["git"]["reason"])
    observation["unknowns"].append("Test commands were discovered only; test outcomes are unverified")
    return observation
