"""测试 overview period=1（近1天=昨日）是否返回数据，并打印 updateTime 与解码日期。"""
import json, os, sys, time, urllib.request
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222; BASE = f"http://127.0.0.1:{PORT}"; MSG = {"n": 0}; ws = None

def http_get(p): return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())
def send(method, params=None):
    MSG["n"] += 1; i = MSG["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}})); return i
def recv_id(i, timeout=25):
    stop = time.time() + timeout
    while time.time() < stop:
        try: raw = ws.recv()
        except Exception: break
        try: m = json.loads(raw)
        except Exception: continue
        if m.get("id") == i: return m
    return None

def main():
    global ws
    sid = sys.argv[1] if len(sys.argv) > 1 else "7643778914138294324"
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.3)
    expr = """(async () => {
      try {
        const r = await fetch('https://music.douyin.com/api/statistics/disclosure/overview?scope=2&songID=%s&period=1', {credentials:'include'});
        const t = await r.text();
        return t.slice(0, 1200);
      } catch(e){ return 'ERR '+String(e); }
    })()""" % sid
    send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
    m = recv_id(MSG["n"], timeout=20)
    v = m.get("result", {}).get("result", {}).get("value") if m else None
    print("RAW:", v)
    try:
        j = json.loads(v)
        ut = j.get("data", {}).get("updateTime")
        if ut:
            import datetime
            dt = datetime.datetime.utcfromtimestamp(int(ut))
            print("updateTime:", ut, "->", dt.strftime("%Y-%m-%d %H:%M UTC"))
        print("metrics:", [(x["metricType"], x["value"]) for x in j.get("data", {}).get("metrics", [])])
    except Exception as e:
        print("parse err", e)
    ws.close()

if __name__ == "__main__":
    main()
