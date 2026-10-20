import json,time,websocket,os

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
    def evals(self,expr,session,timeout=60):
        mid=self.send("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True},session=session)
        r=self.get(mid,timeout)
        if r and "result" in r and "result" in r["result"]: return r["result"]["result"].get("value")
        if r and "error" in r: return "<err "+json.dumps(r["error"],ensure_ascii=False)+">"
        return "<no-result>"

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
    period=202607
    for attempt in range(4):
        expr=f"(async function(){{var base=\"/console/api/v1/settlement/statement/download?time={period}\";try{{var r1=await fetch(base,{{credentials:'include'}});var j=await r1.json();if(j.downloadUrl){{var r2=await fetch(j.downloadUrl,{{credentials:'include'}});var csv=await r2.text();return JSON.stringify({{period:{period},fileName:j.fileName,status:r2.status,len:csv.length,csv:csv}});}}return JSON.stringify({{period:{period},err:JSON.stringify(j)}});}}catch(e){{return JSON.stringify({{period:{period},err:String(e)}});}}}})()"
        res=c.evals(expr,sess,timeout=60)
        try: a=json.loads(res)
        except: print("parse err",res[:200]); continue
        if 'csv' in a:
            path=os.path.join(OUT,f"结算明细_{period}.csv")
            open(path,'w',encoding='utf-8').write(a['csv'])
            lines=a['csv'].splitlines()
            print(f"OK (attempt {attempt}) {period} rows={len(lines)} -> {path}")
            print("  HEADER:",lines[0])
            print("  ROW1:",lines[1] if len(lines)>1 else '')
            return
        else:
            print(f"attempt {attempt} failed: {a.get('err')}")
            time.sleep(3)
    print("ALL RETRIES FAILED for",period)

if __name__=="__main__":
    main()
