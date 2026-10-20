"""从结算页 DOM 提取月度结算表；点击首月「查看明细」，报告其行为(URL/弹窗)与明细内容。"""
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
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.4)
    send("Page.navigate", {"url": "https://music.douyin.com/console/settlement/index"})
    time.sleep(7)
    # 提取月度结算表（按关键词分行解析）
    expr1 = """(() => {
      const lines = (document.body.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
      // 找含 年 月 与 结算成功 的连续行，拼成记录
      const recs = []; let cur = null;
      for (const l of lines) {
        const m = l.match(/^(\\d{4})年(\\d{2})月$/);
        if (m) { if (cur) recs.push(cur); cur = {month: l, amount:null, status:null}; }
        else if (cur) {
          if (/^[\\d.]+$/.test(l) && cur.amount===null) cur.amount = l;
          else if (/结算/.test(l) && cur.status===null) cur.status = l;
        }
      }
      if (cur) recs.push(cur);
      return {url: location.href, recs: recs.slice(0,20)};
    })()"""
    send("Runtime.evaluate", {"expression": expr1, "returnByValue": True})
    m = recv_id(MSG["n"], timeout=15)
    v = m.get("result", {}).get("result", {}).get("value") if m else None
    print("月度结算表:", json.dumps(v, ensure_ascii=False, indent=1))
    # 点击首月 查看明细
    expr2 = """(() => {
      const t = Array.from(document.querySelectorAll('*')).find(e => (e.innerText||'').trim()==='查看明细');
      if (!t) return {err:'no'};
      const before = location.href;
      t.click();
      return {before, after: location.href, tag: t.tagName};
    })()"""
    send("Runtime.evaluate", {"expression": expr2, "returnByValue": True})
    m2 = recv_id(MSG["n"], timeout=15)
    v2 = m2.get("result", {}).get("result", {}).get("value") if m2 else None
    print("点击查看明细:", json.dumps(v2, ensure_ascii=False))
    time.sleep(4)
    # 提取明细区文字（弹窗或新页）
    expr3 = """(() => {
      // 优先弹窗(modal)内的表格文字
      const modal = document.querySelector('[class*=modal],[class*=dialog],[role=dialog]');
      const scope = modal || document.body;
      const txt = (scope.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
      const rel = txt.filter(s => /歌曲|金额|收益|结算|元|分成|播放|单价|计费/.test(s)).slice(0,40);
      return {hasModal: !!modal, rel};
    })()"""
    send("Runtime.evaluate", {"expression": expr3, "returnByValue": True})
    m3 = recv_id(MSG["n"], timeout=15)
    v3 = m3.get("result", {}).get("result", {}).get("value") if m3 else None
    print("明细区:", json.dumps(v3, ensure_ascii=False, indent=1))
    ws.close()

if __name__ == "__main__":
    main()
