import json,time,websocket,urllib.request,ssl

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
SETTLE="https://music.douyin.com/console/settlement/index"
period=202607

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
    expr=f"(async function(){{var base=\"/console/api/v1/settlement/statement/download?time={period}\";var r1=await fetch(base,{{credentials:'include'}});var j=await r1.json();if(!j.downloadUrl)return JSON.stringify({{noUrl:j}});var u=j.downloadUrl;try{{var r2=await fetch(u,{{credentials:'include'}});var csv=await r2.text();return JSON.stringify({{url:u,status:r2.status,len:csv.length,head:csv.slice(0,300)}});}}catch(e){{return JSON.stringify({{url:u,err:String(e)}});}}}})()"
    res=c.evals(expr,sess,timeout=60)
    print("PAGE RES:",res[:1500])
    # try python fetch of the url if present
    try:
        j=json.loads(res)
        u=j.get('url')
        if u:
            print("\nTrying Python urllib on:",u[:120])
            req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':'https://music.douyin.com/'})
            try:
                with urllib.request.urlopen(req,timeout=30) as resp:
                    data=resp.read(500)
                    print("PY STATUS",resp.status,"len",len(data),"head",data[:200])
            except Exception as e:
                print("PY ERR",e)
    except Exception as e:
        print("json err",e)

if __name__=="__main__":
    main()
