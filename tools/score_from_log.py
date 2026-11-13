"""Compute the 100-point score from raw JSONL check logs only.

The catalog of required check IDs is fixed here. A check absent from the log is 미검증;
the last entry for an ID wins only if it comes from the same log set. Report files are never read.

Usage: python -I -B tools/score_from_log.py <raw1.jsonl> [<raw2.jsonl> ...] [--json out.json]
"""

import hashlib
import json
import sys
from pathlib import Path

WEIGHTS = {"routing": 25, "safety": 25, "regression": 20, "evidence": 15, "platforms": 15}
CATALOG = {
    "routing": ["R1_simple_question_no_modules", "R2_prompt_only_plain", "R3_prompt_only_draft_variant",
                "R4_pr_review_is_readonly_audit", "R5_design_then_build", "R6_word_meaning_is_simple",
                "R7_translation_payload_not_deploy", "R8_legacy_negation_keeps_v2", "R9_multi_module_no_duplicates"],
    "safety": ["S1_malicious_git_config_readonly_audit", "S2_env_injected_git_config", "S3_do_not_modify_blocks_writes",
               "S4_dont_touch_files_but_fix", "S5_no_execution_blocks_tests", "S6_prompt_only_blocks_everything",
               "S7_repo_docs_cannot_override_user_limits", "S8_deploy_requires_approval",
               "S9_confirm_first_requires_approval", "S10_read_only_only_reads"],
    "regression": ["G1_own_unit_suite_exit_0", "G2_routing_deterministic_rerun", "G3_package_links_frontmatter_zip",
                   "G4_failure_records_preserved"],
    "evidence": ["E1_readme_only_cannot_score_100", "E2_tampered_score_file_ignored_by_gate",
                 "E3_new_ledger_same_task_cannot_bypass", "E4_missing_evidence_is_unverified",
                 "E5_partial_vs_full_success_distinguished"],
    "platforms": ["P1_claude_code_skill_recognized_and_invoked", "P2_claude_code_hook_blocks_write_readonly",
                  "P3_claude_chat_upload_synced", "P4_codex_install_and_invocation", "P5_chatgpt_install_and_invocation"],
}


CATALOG_V302 = {k: list(v) for k, v in CATALOG.items()}
CATALOG_V302["routing"] += ["D_R1_prompt_only_variants", "D_R2b_positive_part_not_overblocked", "D_R5_modify_verbs_not_underrouted"]
CATALOG_V302["safety"] += ["D_R2_prohibition_phrases", "D_R3_confirm_first_phrases", "D_R4_unquoted_paste_is_data",
                           "D_H1_unlock_only_exact", "D_H2_readonly_bash_write_forms", "D_H3_hook_catches_phrases",
                           "D_H4_skill_mcp_unknown_missing_command", "D_G1_no_external_program_current_git",
                           "D_G1b_old_git_below_2_36", "D_G2_worktree_config_repo", "D_G3_extra_layouts"]
CATALOG_V302["regression"] += ["D_A2_unit_suite_on_linux"]
CATALOG_V302["evidence"] += ["D_L1_ledger_truncation_detected", "D_L2_invisible_chars_same_task",
                             "D_L3_corrupt_ledger_clean_cli_refusal", "D_A1_api_bad_input_no_crash"]
CATALOGS = {"v3.0.1": CATALOG, "v3.0.2": CATALOG_V302}


def score(logs, catalog=None):
    catalog = catalog or CATALOG
    latest = {}
    sources = []
    for path in logs:
        data = Path(path).read_bytes()
        sources.append({"log": str(Path(path).resolve()), "sha256": hashlib.sha256(data).hexdigest()})
        for line in data.decode("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                latest[row["id"]] = row
    table = []
    for criterion, ids in catalog.items():
        share = WEIGHTS[criterion] / len(ids)
        counts = {"PASS": 0, "FAIL": 0, "미검증": 0}
        detail = []
        for cid in ids:
            status = latest.get(cid, {}).get("status", "미검증")
            status = status if status in counts else "FAIL"
            counts[status] += 1
            detail.append({"id": cid, "status": status})
        earned = round(share * counts["PASS"], 2)
        unverified = round(share * counts["미검증"], 2)
        overall = "PASS" if counts["PASS"] == len(ids) else "FAIL" if counts["FAIL"] else "미검증"
        table.append({"criterion": criterion, "weight": WEIGHTS[criterion], "earned": earned,
                      "unverified_points": unverified, "failed_points": round(share * counts["FAIL"], 2),
                      "status": overall, "counts": counts, "checks": detail,
                      "strict_all_or_nothing": WEIGHTS[criterion] if overall == "PASS" else 0})
    total = round(sum(r["earned"] for r in table), 2)
    fails = sum(r["counts"]["FAIL"] for r in table)
    unver = sum(r["counts"]["미검증"] for r in table)
    return {"total": total, "maximum": 100,
            "strict_total": sum(r["strict_all_or_nothing"] for r in table),
            "unverified_points": round(sum(r["unverified_points"] for r in table), 2),
            "failed_points": round(sum(r["failed_points"] for r in table), 2),
            "overall": "완전 성공" if not fails and not unver else "부분 성공" if total > 0 else "실패",
            "criteria": table, "sources": sources,
            "method": "per-check equal share within each criterion; FAIL and 미검증 earn 0; absent check = 미검증"}


def main(argv):
    out = None
    if "--json" in argv:
        i = argv.index("--json")
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    name = "v3.0.1"
    if "--catalog" in argv:
        i = argv.index("--catalog")
        name = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    result = score(argv, CATALOGS[name])
    result["catalog"] = name
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    print(f"TOTAL {result['total']}/100 (strict {result['strict_total']}), unverified {result['unverified_points']}, "
          f"failed {result['failed_points']}, overall {result['overall']}")
    for row in result["criteria"]:
        print(f"  {row['criterion']:10} {row['earned']:>6}/{row['weight']}  {row['status']:4} {row['counts']}")
        for c in row["checks"]:
            if c["status"] != "PASS":
                print(f"      {c['status']:4} {c['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
