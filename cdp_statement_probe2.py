import json,time,websocket

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
SETTLE="https://music.douyin.com/console/settlement/index"

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
    probe='''
    (async function(){
      var base="/console/api/v1/settlement/statement/";
      var cands=[
        base+"download?time=202608",
        base+"download?time=2026-08",
        base+"download?time=20260801",
        base+"download?time=202608&period=202608",
        base+"download?period=202608&month=202608",
        base+"download"
      ];
      var out=[];
      for(var i=0;i<cands.length;i++){
        try{
          var resp=await fetch(cands[i],{credentials:'include',method:'GET'});
          var ct=resp.headers.get('content-type')||'';
          var cd=resp.headers.get('content-disposition')||'';
          var c=resp.clone();
          var txt=await c.text();
          var buf=await resp.arrayBuffer();
          var bytes=new Uint8Array(buf.slice(0,200));
          var snip='';
          for(var j=0;j<bytes.length;j++) snip+=String.fromCharCode(bytes[j]);
          out.push({url:cands[i],status:resp.status,ct:ct,cd:cd,len:buf.byteLength,txtsnip:txt.slice(0,500),hex:snip.slice(0,160)});
        }catch(e){ out.push({url:cands[i],err:String(e)}); }
      }
      return JSON.stringify(out);
    })()
    '''
    res=c.evals(probe,sess,timeout=40)
    try:
        arr=json.loads(res)
        for a in arr:
            print("\n---",a.get('url'),"status",a.get('status'))
            print("  ct:",a.get('ct')," cd:",a.get('cd')," len:",a.get('len'))
            print("  txtsnip:",a.get('txtsnip',a.get('err',''))[:400])
    except Exception as e:
        print("parse err",e,res[:500])

if __name__=="__main__":
    main()
