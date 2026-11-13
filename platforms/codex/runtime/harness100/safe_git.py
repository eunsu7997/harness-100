"""Side-effect-free `git status` for untrusted repositories.

Threats neutralised (P0-1):
- repository config (.git/config): filter/textconv/fsmonitor/hooksPath/sshCommand/includeIf/remotes
  -> git runs against a *shadow* GIT_DIR containing only HEAD, refs and a copy of the index, with a
     config we write. The repository's own config file is never read by git.
- $GIT_DIR/info/attributes, system/global config and attributes -> not visible (shadow dir, NOSYSTEM, GLOBAL=devnull).
- inherited environment (GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT, GIT_EXTERNAL_DIFF, GIT_SSH_COMMAND ...)
  -> git gets a freshly built environment; every inherited GIT_* variable is dropped.
- lazy fetch from promisor remotes / any network -> no remotes in shadow config, GIT_NO_LAZY_FETCH=1,
  protocol.allow=never.
- submodules (their own configs) -> --ignore-submodules=all.
- index refresh writes / locks in the target -> GIT_INDEX_FILE points at a copy; --no-optional-locks.
- executable hijack: the git binary is resolved from PATH only, must not live inside the project,
  and the child process runs with cwd set to the shadow directory, not the repository.

Worktree .gitattributes may still *name* a filter, but without a definition in our config git
treats it as a no-op. Unsupported layouts (linked worktrees, unknown repository extensions) return
status "unknown" instead of falling back to an unsafe call.
The only files written are inside a temporary directory outside the project, removed afterwards.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SAFE_EXTENSIONS = {"objectformat", "refstorage"}


def find_repo(start):
    start = Path(start).resolve()
    for folder in (start, *start.parents):
        dotgit = folder / ".git"
        if dotgit.is_dir():
            return folder, dotgit
        if dotgit.is_file():
            try:
                text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return None, None
            if not text.startswith("gitdir:"):
                return None, None
            gitdir = Path(text[7:].strip())
            gitdir = gitdir if gitdir.is_absolute() else (folder / gitdir)
            return folder, gitdir.resolve()
    return None, None


def read_extensions(config_path):
    """Minimal parse of [core] repositoryformatversion and [extensions]; never executes includes."""
    version, extensions, section = "0", {}, None
    try:
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return version, extensions
    for raw in lines:
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        header = re.match(r"^\[\s*([A-Za-z0-9.-]+)(?:\s+\"[^\"]*\")?\s*\]$", line)
        if header:
            section = header.group(1).lower()
            continue
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if section == "core" and key.lower() == "repositoryformatversion":
            version = value
        elif section == "extensions":
            extensions[key.lower()] = value
    return version, extensions


def resolve_git(project_root):
    path_dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and Path(d).is_absolute()]
    candidate = shutil.which("git", path=os.pathsep.join(path_dirs))
    if not candidate:
        return None
    resolved = Path(candidate).resolve()
    if resolved.is_relative_to(Path(project_root).resolve()):
        return None
    return str(resolved)


def clean_env(shadow, worktree, index, objects, trace_file=None):
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "PATH", "Path", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LANG")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update({
        "HOME": str(shadow), "USERPROFILE": str(shadow), "XDG_CONFIG_HOME": str(shadow),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1",
        "GIT_DIR": str(shadow), "GIT_WORK_TREE": str(worktree), "GIT_INDEX_FILE": str(index),
        "GIT_OBJECT_DIRECTORY": str(objects), "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_PAGER": "cat", "PAGER": "cat",
    })
    if trace_file:
        env["GIT_TRACE"] = str(trace_file)
    return env


def status(project, timeout=15, trace_file=None):
    """Return {"status": "observed"|"unknown", "changes": [...], "dirty": bool, "safety": {...}}."""
    project = Path(project).resolve()
    worktree, gitdir = find_repo(project)
    if worktree is None:
        return {"status": "unknown", "reason": "not a Git repository (no .git found)", "changes": []}
    if (gitdir / "commondir").exists():
        return {"status": "unknown", "reason": "linked worktree is not supported in safe mode", "changes": []}
    version, extensions = read_extensions(gitdir / "config")
    unsupported = sorted(set(extensions) - SAFE_EXTENSIONS)
    if unsupported or version not in ("0", "1"):
        return {"status": "unknown", "reason": f"repository extensions not supported in safe mode: {unsupported}",
                "changes": []}
    git = resolve_git(worktree)
    if not git:
        return {"status": "unknown", "reason": "git executable unavailable outside the project", "changes": []}
    with tempfile.TemporaryDirectory(prefix="h100-safegit-") as tmp:
        shadow = Path(tmp)
        lines = ["[core]", f"\trepositoryformatversion = {version}", "\tbare = false", "\tfsmonitor = false",
                 "\tuntrackedCache = false", f"\thooksPath = {(shadow / 'no-hooks').as_posix()}",
                 f"\tattributesFile = {Path(os.devnull).as_posix()}", "[protocol]", "\tallow = never"]
        if extensions:
            lines.append("[extensions]")
            lines.extend(f"\t{k} = {v}" for k, v in extensions.items())
        (shadow / "config").write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            shutil.copyfile(gitdir / "HEAD", shadow / "HEAD")
            for name in ("packed-refs",):
                if (gitdir / name).is_file():
                    shutil.copyfile(gitdir / name, shadow / name)
            for name in ("refs", "reftable"):
                if (gitdir / name).is_dir():
                    shutil.copytree(gitdir / name, shadow / name, symlinks=False)
            (shadow / "refs").mkdir(exist_ok=True)
            index = shadow / "index"
            if (gitdir / "index").is_file():
                shutil.copyfile(gitdir / "index", index)
        except OSError as error:
            return {"status": "unknown", "reason": f"cannot snapshot repository metadata: {type(error).__name__}",
                    "changes": []}
        relative = project.relative_to(worktree).as_posix() if project != worktree else "."
        command = [git, "--no-optional-locks", "--no-replace-objects",
                   "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                   "-c", f"core.hooksPath={(shadow / 'no-hooks').as_posix()}", "-c", "protocol.allow=never",
                   "-c", "core.sshCommand=false", "-c", "diff.external=", "-c", "submodule.recurse=false",
                   "-c", "safe.directory=*", "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                   "--ignore-submodules=all", "--", relative]
        try:
            result = subprocess.run(command, cwd=str(shadow), capture_output=True, timeout=timeout, check=False,
                                    env=clean_env(shadow, worktree, index, gitdir / "objects", trace_file),
                                    stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"status": "unknown", "reason": type(error).__name__, "changes": []}
    if result.returncode:
        return {"status": "unknown", "reason": "git status failed in safe mode: "
                + result.stderr.decode("utf-8", "replace")[:200], "changes": []}
    prefix = "" if relative == "." else relative.rstrip("/") + "/"
    records = result.stdout.decode("utf-8", errors="replace").split("\0")
    changes, index_pos = [], 0
    while index_pos < len(records):
        record = records[index_pos]
        index_pos += 1
        if not record:
            continue
        code, path = record[:2], record[3:]
        entry = {"status": code, "path": path.removeprefix(prefix)}
        if "R" in code or "C" in code:
            original = records[index_pos] if index_pos < len(records) else ""
            entry["original_path"] = original.removeprefix(prefix) if original.startswith(prefix) else "<outside selected project>"
            index_pos += 1
        if path.startswith(prefix):
            changes.append(entry)
    return {"status": "observed", "changes": changes, "dirty": bool(changes),
            "safety": {"mode": "shadow-gitdir", "repo_config_read_by_git": False, "inherited_git_env": False,
                       "network": "disabled", "submodules": "ignored",
                       "note": "worktree content is hashed raw (no clean filters); filtered files may show as modified"}}
