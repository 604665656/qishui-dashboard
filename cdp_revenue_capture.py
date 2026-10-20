"""导航到控制台 → 点击「歌曲收益」→ 捕获其数据 API（URL + 响应体）。"""
import json, os, sys, time, urllib.request, urllib.parse, base64
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

def main():
    global ws
    wait = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Network.enable", {"maxPostDataSize": 0})
    send("Page.enable"); time.sleep(0.4)
    send("Page.navigate", {"url": "https://music.douyin.com/console/statistics?metricType=6&enter_from=home_data_center"})
    time.sleep(6)
    # 点击「歌曲收益」
    expr = """(() => {
      const els = Array.from(document.querySelectorAll('*'));
      const t = els.find(e => e.children.length===0 && (e.innerText||'').trim()==='歌曲收益');
      if (!t) return 'no-el';
      // 向上找可点击祖先
      let p = t; for (let i=0;i<6;i++){ p=p.parentElement; if(!p) break; }
      t.click(); if (p) p.click();
      return 'clicked';
    })()"""
    send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    recv_id(MSG["n"], timeout=15)
    # 在等待期间接收 Network 响应
    stop = time.time() + wait
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
            rid = m["params"]["requestId"]
            pending[send("Network.getResponseBody", {"requestId": rid})] = rid
        elif mid in pending:
            rid = pending.pop(mid)
            res = m.get("result", {})
            body = res.get("body", "") or ""
            if res.get("base64Encoded") and body:
                body = base64.b64decode(body).decode("utf-8", "ignore")
            resp[rid]["body"] = body
        time.sleep(0.01)
    # 收集 api 响应
    out = []
    for rid, v in resp.items():
        u = v.get("url", "")
        if "api/" in u:
            b = v.get("body", "")
            item = {"url": u, "size": len(b)}
            try: item["json"] = json.loads(b or "{}")
            except Exception:
                if b: item["raw"] = b[:600]
            out.append(item)
    json.dump(out, open("cdp_revenue.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("=== 捕获", len(out), "个 api 响应 ===")
    for r in out:
        u = r.get("url","")
        flag = "★" if any(k in u.lower() for k in ("revenue","income","settle","royalty","profit","收益","结算","account","bill","salary")) else ""
        print(f"  [{r.get('size'):>7}] {flag} {u}")
        if flag:
            print("     ", json.dumps(r.get("json", r.get("raw","")), ensure_ascii=False)[:500])
    ws.close()

if __name__ == "__main__":
    main()
