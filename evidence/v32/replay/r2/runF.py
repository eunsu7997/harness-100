import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: use the local runlib
from runlib import *
base = WORK + r"\runF"
os.makedirs(base, exist_ok=True)

def ok(exp, dec):
    return {"allow": dec == "allow", "defer": dec == "defer", "deny": dec == "deny",
            "not_allow": dec != "allow", "not_deny": dec != "deny", "any": True}[exp]

rows = []
for line in open(os.environ["H100_SETF"], encoding="utf-8"):  # replay copy: set F read from its original path
    it = json.loads(line)
    res, tr, d = run_item(it, base)
    for k, (pr, r) in enumerate(zip(it["probes"], res)):
        rows.append({"id": it["id"], "k": k, "category": it["category"], "mode": pr.get("mode", it["mode"]),
                     "turns": it["turns"], "tool": pr["tool"], "input": pr["input"], "expect": pr["expect"],
                     "decision": r["decision"], "rc": r["rc"], "match": ok(pr["expect"], r["decision"]),
                     "reason": r["reason"]})
with open(OUTDIR + r"\setF-results.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
n = len(rows)
print("probes", n, "matched", sum(r["match"] for r in rows))
for r in rows:
    if not r["match"] or r["rc"] != 0:
        print(r["id"], r["k"], r["category"], r["mode"], r["turns"], r["tool"], json.dumps(r["input"], ensure_ascii=False)[:90], r["expect"], "->", r["decision"], r["rc"])
