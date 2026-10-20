"""导航到结算页 → 捕获月度结算列表 API；再点击首月「查看明细」→ 捕获单曲结算明细 API。"""
import json, os, sys, time, urllib.request, base64
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222; BASE = f"http://127.0.0.1:{PORT}"; MSG = {"n": 0}; ws = None
resp = {}; pending = {}

def http_get(p): return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())
def send(method, params=None):
    MSG["n"] += 1; i = MSG["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}})); return i
def recv_id(i, timeout=30):
    stop = time.time() + timeout
    while time.time() < stop:
        try: raw = ws.recv()
        except Exception: break
        try: m = json.loads(raw)
        except Exception: continue
        if m.get("id") == i: return m
    return None

def drain(secs):
    stop = time.time() + secs
    while time.time() < stop:
        try: raw = ws.recv()
        except Exception: break
        try: m = json.loads(raw)
        except Exception: continue
        mm = m.get("method"); mid = m.get("id")
        if mm == "Network.responseReceived":
            rid = m["params"]["requestId"]
            resp.setdefault(rid, {})["url"] = m["params"].get("response", {}).get("url", "")
            resp[rid]["mime"] = m["params"].get("response", {}).get("mimeType", "")
        elif mm == "Network.loadingFinished":
            pending[send("Network.getResponseBody", {"requestId": rid})] = rid
        elif mid in pending:
            rid = pending.pop(mid)
            r = m.get("result", {})
            b = r.get("body", "") or ""
            if r.get("base64Encoded") and b: b = base64.b64decode(b).decode("utf-8", "ignore")
            resp[rid]["body"] = b
        time.sleep(0.005)

def main():
    global ws
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Network.enable", {"maxPostDataSize": 0})
    send("Page.enable"); time.sleep(0.4)
    send("Page.navigate", {"url": "https://music.douyin.com/console/settlement/index"})
    time.sleep(6)
    # 捕获月度列表 API
    drain(8)
    # 点击首月「查看明细」
    expr = """(() => {
      const els = Array.from(document.querySelectorAll('*'));
      const t = els.find(e => (e.innerText||'').trim()==='查看明细');
      if (!t) return 'no';
      t.click(); return 'clicked';
    })()"""
    send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    recv_id(MSG["n"], timeout=15)
    drain(8)
    # 输出
    out = []
    for rid, v in resp.items():
        u = v.get("url", "")
        if "api/" in u or "settlement" in u or "revenue" in u or "income" in u:
            b = v.get("body", "")
            item = {"url": u, "size": len(b)}
            try: item["json"] = json.loads(b or "{}")
            except Exception:
                if b: item["raw"] = b[:500]
            out.append(item)
    json.dump(out, open("cdp_settle.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("=== 捕获", len(out), "个相关响应 ===")
    for r in out:
        u = r.get("url","")
        print(f"  [{r.get('size'):>7}] {u}")
        if any(k in u.lower() for k in ("settlement","revenue","income","detail","bill","list","month")):
            print("     ", json.dumps(r.get("json", r.get("raw","")), ensure_ascii=False)[:700])
    ws.close()

if __name__ == "__main__":
    main()
