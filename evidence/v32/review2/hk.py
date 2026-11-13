import subprocess, json, os, time
PKG=r"<PROJECT_ROOT>\harness-100-v3.2-cc"
HOOK=PKG+r"\hooks\claude_code_hook.py"
W=r"<TMP>\h100-v32-review2"
def call(ev, state, proc_cwd=None):
    env=dict(os.environ); env["HARNESS100_HOOK_STATE"]=state
    t=time.time()
    p=subprocess.run(["python","-I","-B",HOOK],input=json.dumps(ev,ensure_ascii=False).encode("utf-8"),capture_output=True,env=env,timeout=60,cwd=proc_cwd)
    dt=time.time()-t
    raw=p.stdout
    try: out=raw.decode("utf-8").strip()
    except UnicodeDecodeError: out=raw.decode("cp949","replace").strip()
    dec="defer"
    if out:
        try: dec=json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        except Exception: dec="unparsed"
    if p.returncode==2 and dec=="defer": dec="deny"
    return dict(decision=dec,rc=p.returncode,out=out[:300],err=p.stderr.decode("utf-8","replace")[:200],secs=round(dt,3))

import subprocess as sp
def ensure_fixtures():
    for d in ["proj/src","proj/docs","proj/realdir","proj2/src","outside/sub"]:
        os.makedirs(os.path.join(W,d),exist_ok=True)
    for link,tgt in [("proj/jn","outside"),("jproj","proj"),("proj2/back","proj")]:
        L=os.path.normpath(os.path.join(W,link))
        if not os.path.exists(L):
            sp.run(["cmd","/c","mklink","/J",L,os.path.normpath(os.path.join(W,tgt))],capture_output=True) if False else sp.run(["cmd","/c","mklink","/J",L,os.path.normpath(os.path.join(W,tgt))],capture_output=True)
    L=os.path.join(W,"proj/sl")
    if not os.path.lexists(L):
        try: os.symlink(os.path.join(W,"outside"),L,target_is_directory=True)
        except Exception as e: print("symlink unavailable",e)
    return dict(jn=os.path.exists(os.path.join(W,"proj/jn")),sl=os.path.lexists(L))
