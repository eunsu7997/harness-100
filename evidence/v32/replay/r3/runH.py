import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: local common.py
from common import *
items=[json.loads(l) for l in open(OUT+r"\setH.jsonl",encoding="utf-8")]
res=run_set(items, os.environ["H100_REPLAY_OUT"]+r"\setH-results.jsonl", RV+r"\wH_replay", RV+r"\stH_replay", "H")  # replay copy: output redirected
t=[r for r in res if r["type"]=="tool"]
print(len(t), sum(r["match"] for r in t))
for r in t:
    if not r["match"] or r["secs"]>2: print(r["id"],r["expect"],r["decision"],r["rc"],r["secs"],r["reason"][:80])
