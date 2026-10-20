import json,time,websocket

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
SETTLE="https://music.douyin.com/console/settlement/index"

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
    const x = new _xhr();
    const _open = x.open;
    x.open = function(m,u){ x.__u=u; x.__m=m; return _open.apply(x,arguments); };
    const _send = x.send;
    x.send = function(b){ x.__b=b;
      x.addEventListener('load',()=>{ try{ window.__net.push({type:'xhr',url:String(x.__u),method:String(x.__m),status:x.status,req:String(x.__b||'').slice(0,5000),resp:(x.responseText||'').slice(0,200000)}); }catch(e){} });
      return _send.apply(x,arguments); };
    return x;
  };
  console.log('HOOK_INSTALLED');
})();
"""

class CDP:
    def __init__(self,ws):
        self.ws=websocket.create_connection(ws,timeout=30)
        self.id=0; self.events=[]
    def send(self,method,params=None,session=None):
        self.id+=1
        msg={"id":self.id,"method":method,"params":params or {}}
        if session: msg["sessionId"]=session
        self.ws.send(json.dumps(msg))
        return self.id
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
        # first scan buffered
        for i,e in enumerate(self.events):
            if e.get("method")==method:
                self.events.pop(i); return e
        t=time.time()
        while time.time()-t<timeout:
            m=self._recv(timeout=timeout)
            if m.get("method")==method: return m
            if m.get("id"): pass
        return None
    def evals(self,expr,session,timeout=15):
        mid=self.send("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True},session=session)
        r=self.get(mid,timeout)
        if r and "result" in r and "result" in r["result"]:
            return r["result"]["result"].get("value")
        if r and "error" in r:
            return "<err "+json.dumps(r["error"],ensure_ascii=False)+">"
        return "<no-result>"

def main():
    c=CDP(BROWSER_WS)
    c.send("Target.getTargets"); r=c.get(c.id)
    targets=r.get("result",{}).get("targetInfos",[])
    page=[t for t in targets if t.get("type")=="page"]
    print("pages:",[(t.get("targetId"),t.get("url")) for t in page][:5])
    tid=page[0]["targetId"]
    mid=c.send("Target.attachToTarget",{"targetId":tid,"flatten":True})
    # attach may come as event
    sess=None
    r=c.get(mid,timeout=8)
    if r and "result" in r: sess=r["result"].get("sessionId")
    if not sess:
        ev=c.get_event("Target.attachedToTarget",timeout=8)
        if ev: sess=ev["params"]["sessionId"]
    print("session:",sess)
    c.send("Page.enable",session=sess)
    c.send("Runtime.enable",session=sess)
    c.send("Page.addScriptToEvaluateOnNewDocument",{"source":HOOK},session=sess)
    c.send("Page.reload",session=sess)
    print("reloaded, waiting...")
    time.sleep(10)
    diag=c.evals("JSON.stringify({hook:typeof window.__net, ready:document.readyState, url:location.href, bodyLen:(document.body?document.body.innerHTML.length:-1)})",sess)
    print("DIAG:",diag)
    net=c.evals("JSON.stringify(window.__net||[])",sess)
    print("net raw len:", len(net) if net else 0)
    netj=[]
    try:
        if net and net!="[]": netj=json.loads(net)
    except Exception as e: print("net parse err",e)
    print("captured net entries:",len(netj))
    for e in netj:
        print("  ",e["type"],e["method"],e["status"],e["url"][:150])
    dom=c.evals("(function(){var el=document.querySelector('#root')||document.body;return el?el.innerText.slice(0,5000):'NO_ROOT';})()",sess)
    print("=== DOM TEXT (head) ===")
    print((dom or "")[:3000])
    out={"net":netj,"dom":dom or "","diag":diag}
    with open("cdp_settle_detail.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=1)
    print("saved cdp_settle_detail.json")

if __name__=="__main__":
    main()
