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
        window.__net.push({type:'fetch',url:String(url),method:String(method),status:resp.status,req:String(reqBody).slice(0,8000),resp:txt.slice(0,300000)});
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
      x.addEventListener('load',()=>{ try{ window.__net.push({type:'xhr',url:String(x.__u),method:String(x.__m),status:x.status,req:String(x.__b||'').slice(0,8000),resp:(x.responseText||'').slice(0,300000)}); }catch(e){} });
      return _send.apply(x,arguments); };
    return x;
  };
  console.log('HOOK_INSTALLED');
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
    c.send("Page.reload",session=sess)
    time.sleep(11)
    # find 查看明细 button (leaf node, exact text) + list download-ish
    find='''
    (function(){
      var all=[].slice.call(document.querySelectorAll('*'));
      function leaves(txt){
        return all.filter(function(e){return e.children.length===0 && (e.textContent||'').trim()===txt;});
      }
      var md=leaves('查看明细');
      // also gather any clickable with 下载/明细
      var dl=all.filter(function(e){return /数据下载|明细数据下载|下载明细/.test(e.textContent||'') && e.children.length<=1;});
      var report={md_count:md.length, md_html: md.slice(0,3).map(function(e){return e.outerHTML.slice(0,300);}),
                  dl: dl.slice(0,5).map(function(e){return {tag:e.tagName,cls:(''+e.className).slice(0,80),text:(e.textContent||'').trim().slice(0,40)};})};
      if(md.length){
        var el=md[0];
        report.clicked={tag:el.tagName,cls:(''+el.className).slice(0,80),parent:(el.parentElement?el.parentElement.tagName+'|'+(''+el.parentElement.className).slice(0,60):'')};
        el.click();
      } else {
        report.clicked=null;
      }
      return JSON.stringify(report);
    })()
    '''
    info=c.evals(find,sess)
    print("CLICK INFO:",info)
    print("waiting for detail API...")
    time.sleep(6)
    net=c.evals("JSON.stringify(window.__net||[])",sess)
    netj=json.loads(net) if net and net!="[]" else []
    # show entries after order list (the detail ones) - print all settle_audit urls
    print("total net:",len(netj))
    for e in netj:
        if 'settle_audit' in e['url'] or 'detail' in e['url'].lower() or 'bill' in e['url'].lower():
            print('\n====',e['type'],e['method'],e['status'],e['url'])
            print('RESP(len=%d):'%len(e.get('resp','')), e.get('resp','')[:3000])
    # try to grab modal/table DOM
    modal=c.evals("(function(){var m=document.querySelector('[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog]');if(m)return m.innerText.slice(0,3000);var t=document.body.innerText;return 'NO_MODAL; bodyTail='+t.slice(-1500);})()",sess)
    print("\n=== MODAL/DOM TAIL ===")
    print((modal or "")[:3000])
    out={"net":netj,"click_info":info,"modal":modal}
    with open("cdp_settle_click.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=1)
    print("saved cdp_settle_click.json")

if __name__=="__main__":
    main()
