import os
import sys,json,os,time,shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # replay copy: local hk.py
from hk import *
ensure_fixtures()
EV = os.environ["H100_REPLAY_OUT"]  # replay copy: output dir
def ok(exp,d):
    return {"allow":d=="allow","defer":d=="defer","deny":d=="deny","not_allow":d!="allow","not_deny":d!="deny","any":True}[exp]
res=[]
for line in open(os.environ["H100_SETI"],encoding="utf-8"):
    it=json.loads(line); steps=[]
    S=W+"\state_setI2\\"+it["id"]; shutil.rmtree(S,ignore_errors=True); os.makedirs(S)
    for st in it["steps"]:
        if st["type"]=="prompt":
            r=call({"hook_event_name":"UserPromptSubmit","session_id":st["session"],"prompt":st["text"],"cwd":st["cwd"]},S)
            steps.append({"type":"prompt","text":st["text"][:60],"rc":r["rc"],"secs":r["secs"]})
        else:
            ev={"hook_event_name":"PreToolUse","session_id":st["session"],"tool_name":st["tool"],"tool_input":st["input"],"permission_mode":st.get("mode",it["mode"]),"cwd":st["cwd"]}
            r=call(ev,S)
            steps.append({"type":"tool","tool":st["tool"],"input":st["input"],"session":st["session"][:40],"cwd":st["cwd"],"expect":st["expect"],"decision":r["decision"],"rc":r["rc"],"match":ok(st["expect"],r["decision"]),"secs":r["secs"],"reason":r["out"][:200],"err":r["err"]})
    res.append({"id":it["id"],"category":it["category"],"mode":it["mode"],"steps":steps})
with open(EV+r"\setI-results.jsonl","w",encoding="utf-8") as f:
    for r in res: f.write(json.dumps(r,ensure_ascii=False)+"\n")
tools=[s for r in res for s in r["steps"] if s["type"]=="tool"]
print("probes",len(tools),"matched",sum(s["match"] for s in tools))
for r in res:
    for s in r["steps"]:
        if s["type"]=="tool" and not s["match"]: print(r["id"],s["expect"],s["decision"],str(s["input"])[:70],s["cwd"][-12:],s["reason"][-90:] )
print("max secs",max(s["secs"] for r in res for s in r["steps"]))
