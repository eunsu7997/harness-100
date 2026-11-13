"""v3.3 evidence helper: compare allow decisions of two replay/result files row by row (read-only).

Usage: python -I -B -X utf8 tools/v33_allow_diff.py <old.jsonl> <new.jsonl> [label]
Prints allow counts and the ids that are allow only in the new file (need judging) or only in the old one.
"""
import json
import sys


def rows(path):
    out = {}
    for line in open(path, encoding="utf-8").read().split("\n"):
        if not line.strip():
            continue
        r = json.loads(line)
        if "steps" in r and isinstance(r["steps"], list):  # set I format: one row per item, nested steps
            for i, s in enumerate(r["steps"]):
                if s.get("type") == "tool":
                    out[(r["id"], i)] = s
            continue
        key = (r.get("id"), r.get("step", r.get("probe", r.get("k", 0))))
        out[key] = r
    return out


def main():
    old, new = rows(sys.argv[1]), rows(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) > 3 else sys.argv[2]
    a_old = {k for k, r in old.items() if r.get("decision") == "allow"}
    a_new = {k for k, r in new.items() if r.get("decision") == "allow"}
    print(f"== {label}: rows old {len(old)} new {len(new)}; allow old {len(a_old)} new {len(a_new)}")
    for k in sorted(a_new - a_old, key=str):
        r = new[k]
        print("  NEW-ALLOW", k, r.get("tool"), json.dumps(r.get("input"), ensure_ascii=False)[:160],
              (r.get("turns") or r.get("grant") or "")[:1] if isinstance(r.get("turns"), list) else r.get("grant", ""))
    gone = sorted(a_old - a_new, key=str)
    print("  allow->not allow:", len(gone), " ".join(str(k[0]) for k in gone[:80]))


if __name__ == "__main__":
    main()
