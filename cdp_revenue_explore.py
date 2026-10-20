"""探索当前收益页 DOM：提取可见文字 + 收益/月/明细/歌曲 相关元素与链接。"""
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
    tabs = http_get("/json")
    tab = next((t for t in tabs if t.get("url","").startswith("http")), None)
    print("当前 tab url:", tab.get("url"))
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.5)
    expr = """(() => {
      const txt = (document.body.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
      // 收益/月/明细/歌曲 相关
      const rel = txt.filter(s => /收益|收入|月|明细|结算|分成|歌曲|金额|元|账单/.test(s));
      // 链接
      const links = Array.from(document.querySelectorAll('a, [href], [role=tab], [class*=tab]'))
        .map(e=>({t:(e.innerText||'').trim(), h:e.getAttribute('href')||''}))
        .filter(x=>/收益|收入|月|明细|结算|歌曲|revenue|income|settle|bill/.test(x.t+x.h));
      return {url: location.href, rel: rel.slice(0,80), links: links.slice(0,40)};
    })()"""
    send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    m = recv_id(MSG["n"], timeout=20)
    v = m.get("result", {}).get("result", {}).get("value") if m else None
    print(json.dumps(v, ensure_ascii=False, indent=1))
    ws.close()

if __name__ == "__main__":
    main()
