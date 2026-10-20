import json,time,websocket

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
DC="https://music.douyin.com/console"

HOOK = r"""
(function(){
  window.__net = window.__net || [];
  const _fetch = window.fetch ? window.fetch.bind(window) : null;
  if(_fetch){
    window.fetch = function(input, init){
      const url = (typeof input==='string')?input:(input&&input.url)||'';
      const method=(init&&init.method)||'GET';
      const reqBody = init&&init.body? (typeof init.body==='string'?init.body:'<body>') : '';
      return _fetch(input, init).then(async resp=>{
        let txt=''; try{ txt = await resp.clone().text(); }catch(e){ txt='<err '+e.message+'>'; }
        window.__net.push({type:'fetch',url:String(url),method:String(method),status:resp.status,req:String(reqBody).slice(0,5000),resp:txt.slice(0,200000)});
        return resp;
      });
    };
  }
  const _xhr = window.XMLHttpRequest;
  window.XMLHttpRequest = function(){
    const x = new _xhr(); const _open=x.open;
    x.open=function(m,u){x.__u=u;x.__m=m;return _open.apply(x,arguments);};
    const _send=x.send; x.send=function(b){x.__b=b;
      x.addEventListener('load',()=>{try{window.__net.push({type:'xhr',url:String(x.__u),method:String(x.__m),status:x.status,req:String(x.__b||'').slice(0,5000),resp:(x.responseText||'').slice(0,200000)});}catch(e){}});
      return _send.apply(x,arguments);};
    return x;
  };
})();
"""

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
    def evals(self,expr,session,timeout=15):
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
    c.send("Page.addScriptToEvaluateOnNewDocument",{"source":HOOK},session=sess)
    c.send("Page.navigate",{"url":DC},session=sess)
    time.sleep(12)
    # capture net urls containing statistics/play/trend/month/data
    net=c.evals("JSON.stringify(window.__net||[])",sess)
    netj=json.loads(net) if net and net!="[]" else []
    print("total net:",len(netj))
    keys=('statistics','trend','month','play','overview','data-','analytics','luna','douyin','song','report','panel','chart')
    hits=[e for e in netj if any(k in e['url'].lower() for k in keys) and 'static' not in e['url'] and 'monitor' not in e['url'] and 'mcs.' not in e['url']]
    print("candidate stat urls:",len(hits))
    for e in hits[:40]:
        print("  ",e['method'],e['status'],e['url'][:140])
    # also save
    with open("cdp_datacenter.json","w",encoding="utf-8") as f: json.dump(netj,f,ensure_ascii=False,indent=1)
    print("saved cdp_datacenter.json")

if __name__=="__main__":
    main()
