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
    # poll for settlement table
    ready=False
    for _ in range(20):
        time.sleep(2)
        bt=c.evals("(document.body?document.body.innerText:'').indexOf('结算时间')>=0",sess)
        if bt=="true": ready=True; break
    print("settlement table ready:",ready)
    # locate candidates
    loc='''
    (function(){
      var all=[].slice.call(document.querySelectorAll('*'));
      function dc(e){return e.getElementsByTagName('*').length;}
      function pick(re){var a=all.filter(function(e){return re.test(e.textContent||'')&&dc(e)<=4;});a.sort(function(x,y){return dc(x)-dc(y);});return a;}
      var dl=pick(/明细数据下载|数据下载/);
      var md=pick(/查看明细/);
      var rep={dl:dl.slice(0,4).map(function(e){return {tag:e.tagName,cls:(''+e.className).slice(0,70),text:(e.textContent||'').trim().slice(0,30)};}),
               md:md.slice(0,4).map(function(e){return {tag:e.tagName,cls:(''+e.className).slice(0,70),text:(e.textContent||'').trim().slice(0,30)};})};
      // click first 查看明细 (per-month detail)
      var target=md[0]||dl[0];
      if(target){target.click();rep.clicked={tag:target.tagName,cls:(''+target.className).slice(0,70),text:(target.textContent||'').trim().slice(0,30)};}
      else rep.clicked=null;
      return JSON.stringify(rep);
    })()
    '''
    rep=c.evals(loc,sess)
    print("LOC REP:",rep)
    print("waiting for triggered API...")
    time.sleep(8)
    net=c.evals("JSON.stringify(window.__net||[])",sess)
    netj=json.loads(net) if net and net!="[]" else []
    print("total net:",len(netj))
    # print any new-ish settlement urls beyond the known list
    known=['get_session','query_role_event_message','get_settle_notice_info','query_audit_order','get_quiz_and_answer','get_recalling_order','get_config','account_component','fetch_latest','query_account_scores']
    staticish=['/static/','remote.js','settle-bundle','.js','.css','builder-runtime','lib-']
    for e in netj:
        if 'wallet-settle' in e['url'] and not any(k in e['url'] for k in known) and not any(s in e['url'] for s in staticish):
            print('\n==== NEW',e['type'],e['method'],e['status'],e['url'])
            print('RESP(len=%d):'%len(e.get('resp','')), e.get('resp','')[:5000])
    # capture modal DOM after click
    modal=c.evals("(function(){var m=document.querySelector('[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=Drawer],[class*=drawer]');if(m)return m.innerText.slice(0,4000);var t=document.body.innerText;return 'NO_MODAL; tail='+t.slice(-2000);})()",sess)
    print("\n=== MODAL/DOM ===")
    print((modal or "")[:4000])
    # also list all wallet-settle urls with lengths for inspection
    print("\n--- all wallet-settle urls ---")
    for e in netj:
        if 'wallet-settle' in e['url']:
            print(' ',e['method'],'len=%d'%len(e.get('resp','')),e['url'][:120])
    out={"net":netj,"loc":rep}
    with open("cdp_settle_detail3.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=1)
    print("saved cdp_settle_detail3.json")

if __name__=="__main__":
    main()
