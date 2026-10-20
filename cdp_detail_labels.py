"""导航到单曲详情页，提取 8 个指标的 标签->值 映射，并探测标签文字。"""
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
    song_id = sys.argv[1] if len(sys.argv) > 1 else "7643778914138294324"
    url = f"https://music.douyin.com/console/statistics/song/{song_id}?songForm=1"
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.3)
    send("Page.navigate", {"url": url}); time.sleep(5)
    # 提取指标卡片：找含数字值的元素及其前导标签
    expr = """(() => {
      const out = [];
      // 通用：找所有叶子文本节点配对（标签 + 数字）
      const walk = (el, depth) => {
        if (depth>12) return;
        for (const c of el.children) {
          const t = (c.innerText||'').replace(/\\s+/g,' ').trim();
          if (t && /[\\u4e00-\\u9fa5]/.test(t) && /\\d/.test(t)) out.push(t);
          walk(c, depth+1);
        }
      };
      walk(document.body, 0);
      // 也尝试找指标容器
      const cards = Array.from(document.querySelectorAll('[class*=metric],[class*=indicator],[class*=stat],[class*=card]'))
        .map(c=>(c.innerText||'').replace(/\\s+/g,' ').trim()).filter(s=>s.length>0 && s.length<60);
      return {pairs: out.slice(0,80), cards: cards.slice(0,40)};
    })()"""
    send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    m = recv_id(MSG["n"], timeout=20)
    v = m.get("result",{}).get("result",{}).get("value") if m else None
    print(json.dumps(v, ensure_ascii=False, indent=1))
    ws.close()

if __name__ == "__main__":
    main()
