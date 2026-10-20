import json,time,websocket,urllib.request,os,ssl

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
SETTLE="https://music.douyin.com/console/settlement/index"
OUT="C:/Users/60466/WorkBuddy/2026-10-17-14-52-57/结算明细"
os.makedirs(OUT,exist_ok=True)

class CDP:
    def __init__(self,ws):
        self.ws=websocket.create_connection(ws,timeout=30); self.id=0; self.events=[]
    def send(self,method,params=None,session=None):
        self.id+=1; msg={"id":self.id,"method":method,"params":params or {}}
        if session: msg["sessionId"]=session
        self.ws.send(json.dumps(msg)); return self.id
    def _recv(self,timeout=30):
        self.ws.settimeout(timeout)
        try: return json.loads(self.ws.recv())
        except Exception as e: return {"_err":str(e)}
    def get(self,mid,timeout=20):
        t=time.time()
        while time.time()-t<timeout:
            m=self._recv(timeout=timeout)
            if m.get("id")==mid: return m
            if m.get("method"): self.events.append(m)
        return None
    def get_event(self,method,timeout=20):
        for i,e in enumerate(self.events):
            if e.get("method")==method: self.events.pop(i); return e
        t=time.time()
        while time.time()-t<timeout:
            m=self._recv(timeout=timeout)
            if m.get("method")==method: return m
        return None
    def evals(self,expr,session,timeout=30):
        mid=self.send("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True},session=session)
        r=self.get(mid,timeout)
        if r and "result" in r and "result" in r["result"]: return r["result"]["result"].get("value")
        if r and "error" in r: return "<err "+json.dumps(r["error"],ensure_ascii=False)+">"
        return "<no-result>"

def get_url(period,sess,c):
    expr=f"(async function(){{var base=\"/console/api/v1/settlement/statement/download?time={period}\";try{{var r1=await fetch(base,{{credentials:'include'}});var j=await r1.json();return JSON.stringify({{period:{period},downloadUrl:j.downloadUrl||null,fileName:j.fileName||null,err:j.errMsg||null}});}}catch(e){{return JSON.stringify({{period:{period},err:String(e)}});}}}})()"
    return c.evals(expr,sess,timeout=30)

def py_download(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://music.douyin.com/'})
    with urllib.request.urlopen(req,timeout=60) as resp:
        return resp.read().decode('utf-8','replace'), resp.status

def main():
    c=CDP(BROWSER_WS)
    c.send("Target.getTargets"); r=c.get(c.id)
    tid=[t for t in r["result"]["targetInfos"] if t.get("type")=="page"][0]["targetId"]
    mid=c.send("Target.attachToTarget",{"targetId":tid,"flatten":True}); sess=None
    r=c.get(mid,timeout=8)
    if r and "result" in r: sess=r["result"].get("sessionId")
    if not sess:
        ev=c.get_event("Target.attachedToTarget",timeout=8); sess=ev["params"]["sessionId"]
    c.send("Page.enable",session=sess); c.send("Runtime.enable",session=sess)
    c.send("Page.navigate",{"url":SETTLE},session=sess)
    time.sleep(6)
    periods=[202604,202605,202606,202607,202608]
    for p in periods:
        got=None
        for attempt in range(3):
            j=json.loads(get_url(p,sess,c))
            if j.get('downloadUrl'):
                got=j; break
            print(f"  get_url {p} attempt {attempt} err:",j.get('err')); time.sleep(2)
        if not got or not got.get('downloadUrl'):
            print(f"FAIL get url {p}"); continue
        # download via python immediately
        ok=False
        for attempt in range(3):
            try:
                csv,st=py_download(got['downloadUrl'])
                if st==200 and csv:
                    path=os.path.join(OUT,f"结算明细_{p}.csv")
                    open(path,'w',encoding='utf-8').write(csv)
                    lines=csv.splitlines()
                    print(f"OK {p} rows={len(lines)} -> {path}")
                    print("   HEADER:",lines[0])
                    ok=True; break
            except Exception as e:
                print(f"  py_download {p} attempt {attempt} err:",e); time.sleep(2)
        if not ok: print(f"FAIL download {p}")
    print("DONE")

if __name__=="__main__":
    main()
