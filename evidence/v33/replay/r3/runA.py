import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: local common.py
from common import *
items=[json.loads(l) for l in open(OUT+r"\attacks.jsonl",encoding="utf-8")]
res=run_set(items, os.environ["H100_REPLAY_OUT"]+r"\attacks-results-r3.jsonl", RV+r"\wA_replay", RV+r"\stA_replay", "A")  # replay copy: output redirected
t=[r for r in res if r["type"]=="tool"]
print(len(items), len(t), sum(r["match"] for r in t))
print("ALLOWS")
for r in t:
    if r["decision"]=="allow": print(r["id"],r["expect"],json.dumps(r["input"],ensure_ascii=False)[:200])
print("EXIT2/slow/odd")
for r in res:
    if r["rc"] not in (0,) and r["type"]!="state" or r.get("secs",0)>2 or r.get("decision") in("TIMEOUT","unparsed"): print(r["id"],r["type"],r["rc"],r["decision"],r["secs"],r.get("stderr","")[:100])
print("max", max(r.get("secs",0) for r in res))
