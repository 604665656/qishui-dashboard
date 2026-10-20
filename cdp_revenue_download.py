import json,time,websocket

BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
SETTLE="https://music.douyin.com/console/settlement/index"

HOOK = r"""
(function(){
  window.__net = window.__net || [];
  window.__dl = window.__dl || [];
  var _open=window.open?window.open.bind(window):null;
  window.open=function(u){ try{window.__dl.push({type:'window.open',url:String(u)});}catch(e){} return _open?_open.apply(window,arguments):null; };
  var _ac=HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click=function(){ try{ if(this.href) window.__dl.push({type:'anchor',href:this.href,download:this.download,text:(this.textContent||'').trim().slice(0,40)}); }catch(e){} return _ac.apply(this,arguments); };
  const _fetch = window.fetch ? window.fetch.bind(window) : null;
  if(_fetch){
    window.fetch = function(input, init){
      const url = (typeof input==='string')?input:(input&&input.url)||'';
      const method=(init&&init.method)||'GET';
      const reqBody = init&&init.body? (typeof init.body==='string'?init.body:'<body>') : '';
      return _fetch(input, init).then(async resp=>{
        let txt=''; try{ txt = await resp.clone().text(); }catch(e){ txt='<err '+e.message+'>'; }
        window.__net.push({type:'fetch',url:String(url),method:String(method),status:resp.status,req:String(reqBody).slice(0,8000),resp:txt.slice(0,400000)});
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
      x.addEventListener('load',()=>{ try{ window.__net.push({type:'xhr',url:String(x.__u),method:String(x.__m),status:x.status,req:String(x.__b||'').slice(0,8000),resp:(x.responseText||'').slice(0,400000)}); }catch(e){} });
      return _send.apply(x,arguments); };
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
    c.send("Page.navigate",{"url":SETTLE},session=sess)
    time.sleep(12)
    # click 歌曲结算明细数据下载
    loc='''
    (function(){
      var all=[].slice.call(document.querySelectorAll('*'));
      function dc(e){return e.getElementsByTagName('*').length;}
      var dl=all.filter(function(e){return /明细数据下载|数据下载/.test(e.textContent||'')&&dc(e)<=4;});
      dl.sort(function(x,y){return dc(x)-dc(y);});
      if(dl[0]){dl[0].click();return JSON.stringify({clicked:true,cls:(''+dl[0].className).slice(0,80)});}
      return JSON.stringify({clicked:false});
    })()
    '''
    rep=c.evals(loc,sess)
    print("CLICK DL:",rep)
    time.sleep(8)
    net=c.evals("JSON.stringify(window.__net||[])",sess)
    dl=c.evals("JSON.stringify(window.__dl||[])",sess)
    netj=json.loads(net) if net and net!="[]" else []
    dlj=json.loads(dl) if dl and dl!="[]" else []
    print("net:",len(netj)," dl captures:",len(dlj))
    print("=== DL CAPTURES ===")
    for d in dlj: print(json.dumps(d,ensure_ascii=False))
    print("=== NEW non-static net urls ===")
    staticish=['/static/','remote.js','settle-bundle','.js','.css','builder-runtime','lib-']
    for e in netj:
        if not any(s in e['url'] for s in staticish) and ('settle' in e['url'].lower() or 'bill' in e['url'].lower() or 'export' in e['url'].lower() or 'download' in e['url'].lower() or 'excel' in e['url'].lower() or 'file' in e['url'].lower()):
            print('\n',e['type'],e['method'],e['status'],e['url'])
            print('RESP(len=%d):'%len(e.get('resp','')), e.get('resp','')[:3000])
    out={"net":netj,"dl":dlj,"click":rep}
    with open("revenue_capture.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=1)
    print("saved revenue_capture.json")

if __name__=="__main__":
    main()
