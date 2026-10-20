import json,time,websocket
BROWSER_WS="ws://127.0.0.1:9222/devtools/browser/0c3d551e-2ccf-4c71-aca3-48869a0af6bc"
DC="https://music.douyin.com/console"
class CDP:
    def __init__(s): s.ws=websocket.create_connection(BROWSER_WS,timeout=30); s.id=0; s.events=[]
    def send(s,m,p=None,se=None):
        s.id+=1; msg={"id":s.id,"method":m,"params":p or {}}
        if se: msg["sessionId"]=se
        s.ws.send(json.dumps(msg)); return s.id
    def _r(s,t=30):
        s.ws.settimeout(t)
        try: return json.loads(s.ws.recv())
        except Exception as e: return {"_err":str(e)}
    def get(s,mid,t=20):
        x=time.time()
        while time.time()-x<t:
            m=s._r(t)
            if m.get("id")==mid: return m
            if m.get("method"): s.events.append(m)
        return None
    def ge(s,m,t=20):
        for i,e in enumerate(s.events):
            if e.get("method")==m: s.events.pop(i); return e
        x=time.time()
        while time.time()-x<t:
            m=s._r(t)
            if m.get("method")==m: return m
        return None
    def ev(s,e,se,t=20):
        mid=s.send("Runtime.evaluate",{"expression":e,"returnByValue":True,"awaitPromise":True},se); r=s.get(mid,t)
        if r and "result" in r: return r["result"]["result"].get("value")
        return ""
c=CDP()
c.send("Target.getTargets"); r=c.get(c.id)
tid=[t for t in r["result"]["targetInfos"] if t.get("type")=="page"][0]["targetId"]
c.send("Target.attachToTarget",{"targetId":tid,"flatten":True}); r=c.get(c.id,8)
sess=r.get("sessionId") if "result" in r else c.ge("Target.attachedToTarget")["params"]["sessionId"]
c.send("Page.enable",session=sess); c.send("Runtime.enable",session=sess)
c.send("Page.navigate",{"url":DC},session=sess)
time.sleep(10)
probe='''
(async function(){
  var periods=[1,2,3,4,30,90];
  var out=[];
  for(var i=0;i<periods.length;i++){
    try{
      var r=await fetch("/api/statistics/disclosure/home-preview?period="+periods[i],{credentials:"include"});
      var j=await r.json();
      out.push({period:periods[i],data:j.data});
    }catch(e){ out.push({period:periods[i],err:String(e)}); }
  }
  return JSON.stringify(out);
})()
'''
res=c.ev(probe,sess,30)
print(res[:3000])
PY=0
