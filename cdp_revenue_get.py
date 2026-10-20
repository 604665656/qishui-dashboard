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
    def _recv(selftimeout=30):
        self.ws.settimeout(self._recv.timeout if hasattr(self._recv,'timeout') else 30)
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
    periods=[202604,202605,202606,202607,202608]
    fetchall='''
    (async function(){
      var periods=arguments[0];
      var base="/console/api/v1/settlement/statement/download?time=";
      var res=[];
      for(var i=0;i<periods.length;i++){
        try{
          var r1=await fetch(base+periods[i],{credentials:'include'});
          var j=await r1.json();
          if(j.downloadUrl){
            var r2=await fetch(j.downloadUrl,{credentials:'include'});
            var csv=await r2.text();
            res.push({period:periods[i],fileName:j.fileName,status:r2.status,len:csv.length,csv:csv});
          } else {
            res.push({period:periods[i],err:JSON.stringify(j)});
          }
        }catch(e){ res.push({period:periods[i],err:String(e)}); }
      }
      return JSON.stringify(res);
    })()
    '''
    # build args via separate evaluate passing periods as JSON
    expr=f"(async function(){{var periods={json.dumps(periods)};var base=\"/console/api/v1/settlement/statement/download?time=\";var res=[];for(var i=0;i<periods.length;i++){{try{{var r1=await fetch(base+periods[i],{{credentials:'include'}});var j=await r1.json();if(j.downloadUrl){{var r2=await fetch(j.downloadUrl,{{credentials:'include'}});var csv=await r2.text();res.push({{period:periods[i],fileName:j.fileName,status:r2.status,len:csv.length,csv:csv}});}}else{{res.push({{period:periods[i],err:JSON.stringify(j)}});}}}}catch(e){{res.push({{period:periods[i],err:String(e)}});}}}}return JSON.stringify(res);}})()"
    res=c.evals(expr,sess,timeout=90)
    try:
        arr=json.loads(res)
    except Exception as e:
        print("parse err",e,res[:300]); return
    for a in arr:
        p=a.get('period'); fn=a.get('fileName','')
        if 'csv' in a:
            path=os.path.join(OUT,f"结算明细_{p}.csv")
            with open(path,'w',encoding='utf-8') as f: f.write(a['csv'])
            # preview header + first 2 lines
            lines=a['csv'].splitlines()
            print(f"OK {p} file={fn} rows={len(lines)} -> {path}")
            print("   HEADER:",lines[0] if lines else '')
            print("   ROW1:",lines[1] if len(lines)>1 else '')
        else:
            print(f"FAIL {p}:",a.get('err'))
    print("DONE")

if __name__=="__main__":
    main()
