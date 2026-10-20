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
    def evals(self,expr,session,timeout=40):
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
    ono={'202607':'TT7676541649912859443','202608':'TT7687016259842214690'}
    for p,o in ono.items():
        expr=f"(async function(){{try{{var r=await fetch('https://wallet-settle.bytedance.com/settle_audit_business/bill/get_role_bill/?settle_order_no={o}&game_id=',{{credentials:'include'}});var j=await r.json();var rb=j.data.role_bill.role_bill_node;function walk(n,depth){{var s=n.node_name+':'+n.role_amount;return s+(n.sub_nodes||[]).map(function(x){{return ' | '+walk(x,depth+1);}}).join('');}}return JSON.stringify({{cycle:j.data.role_bill.settle_cycle, sum:j.data.role_bill.role_bill_node.role_amount, tree:walk(rb,0)}});}}catch(e){{return JSON.stringify({{err:String(e)}});}}}})()"
        res=c.evals(expr,sess,timeout=30)
        print(p,"=>",res[:1200])

if __name__=="__main__":
    main()
