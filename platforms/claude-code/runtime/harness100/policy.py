"""Action decisions only. No commands are executed by this module.

Order of evaluation (first match wins):
1. unknown action -> deny
2. capability not granted by the route (user constraints already removed it) -> deny
3. exact target inside the declared workspace, no overwrite on create -> else deny
4. approval-required action (risky, or any non-read action under confirm_first) -> approval_required
   unless an Approval names this exact action and target
5. allow (the host must re-check immediately before acting)
"""

from dataclasses import dataclass
from pathlib import Path

ACTION_CAPABILITY = {
    "read_project": "read", "run_tests": "execute", "create_file": "write", "modify_file": "write",
    "overwrite_existing": "write", "risky_local": "write", "git_commit": "write",
    "delete_existing": "delete", "deploy": "deploy", "git_push": "deploy",
    "external_send": "network", "network": "network", "install_dependency": "install", "paid_call": "network",
}
ALWAYS_APPROVAL = {"risky_local", "overwrite_existing", "delete_existing", "deploy", "git_push", "git_commit",
                   "external_send", "network", "install_dependency", "paid_call"}
CONSTRAINT_REASON = {"write": "no_modify", "execute": "no_execute", "deploy": "no_deploy", "delete": "no_delete",
                     "network": "no_network", "install": "no_install"}


@dataclass(frozen=True)
class Approval:
    """Must be created by the host from a user confirmation, never from project content."""
    action: str
    target: str


def gate(action, decision, target=None, workspace=None, approvals=()):
    def result(status, reason):
        return {"status": status, "action": action, "reason": reason}

    if action not in ACTION_CAPABILITY:
        return result("deny", "Unknown action has no execution authorization")
    policy = decision.get("policy", {})
    caps = set(policy.get("capabilities", decision.get("capabilities", [])))
    constraints = set(policy.get("constraints", decision.get("constraints", [])))
    needed = ACTION_CAPABILITY[action]
    if needed not in caps:
        if "prompt_only" in constraints:
            return result("deny", "User asked for a prompt only: no tools, probes or changes")
        if constraints & {"read_only", "analyze_only"} and needed != "read":
            return result("deny", "User restricted this task to reading/analysis")
        blocker = CONSTRAINT_REASON.get(needed)
        if blocker in constraints:
            return result("deny", f"User constraint {blocker} forbids this action")
        return result("deny", "Action is outside the capabilities of the selected task")
    if action in ("create_file", "overwrite_existing") and "no_create" in constraints:
        return result("deny", "User constraint no_create forbids creating new files")
    if workspace is None or target is None:
        return result("deny", "An exact target and workspace are required")
    root = Path(workspace).resolve()
    path = Path(target).resolve()
    if not root.is_dir() or not path.is_relative_to(root):
        return result("deny", "Target is outside the allowed workspace")
    if action == "create_file" and path.exists():
        return result("deny", "Existing user files cannot be overwritten by create_file")
    approved = any(isinstance(item, Approval) and item.action == action and Path(item.target).resolve() == path
                   for item in approvals)
    if needed != "read" and not approved:
        # v3.2 fix 4 (gate = hook): an action with side effects is allowed only by a user approval that names this
        # exact action and target (the gate's equivalent of a grant). Sentence interpretation never allows.
        return result("approval_required", "Approval must name this exact action and target")
    return result("allow", "Within task scope and user constraints; host must re-check immediately before acting")
