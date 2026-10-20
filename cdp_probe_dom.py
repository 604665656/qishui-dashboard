"""探测统计页 DOM：指标 tab 标签、表格列头、以及页面里的请求签名客户端全局变量。"""
import json, os, sys, time, urllib.request, urllib.parse
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222
BASE = f"http://127.0.0.1:{PORT}"
msg_id = {"n": 0}
ws = None

def http_get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())

def send(method, params=None):
    msg_id["n"] += 1
    i = msg_id["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    return i

def recv_until(pred, timeout=30):
    stop = time.time() + timeout
    while time.time() < stop:
        try:
            raw = ws.recv()
        except Exception:
            break
        try:
            m = json.loads(raw)
        except Exception:
            continue
        if pred(m):
            return m
    return None

def main():
    global ws
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://music.douyin.com/console/statistics?metricType=6&enter_from=home_data_center"
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    if not tab:
        newt = http_get("/json/new?" + urllib.parse.quote(url, safe=":"))
        ws_url = newt["webSocketDebuggerUrl"]
    else:
        ws_url = tab["webSocketDebuggerUrl"]
    ws = create_connection(ws_url, timeout=60)
    send("Page.enable"); send("Runtime.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": url})
    # 等页面加载 + 指标渲染
    time.sleep(4)
    # 1) 提取可见文字（指标tab、列头）
    expr1 = """(() => {
      const txt = (el)=> (el&&el.innerText||'').replace(/\\s+/g,' ').trim();
      const headers = Array.from(document.querySelectorAll('th, [class*=header], [class*=column]')).map(txt).filter(Boolean).slice(0,40);
      const tabs = Array.from(document.querySelectorAll('[class*=tab], [role=tab]')).map(txt).filter(Boolean).slice(0,40);
      const allText = (document.body.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean).slice(0,60);
      return {headers, tabs, allText};
    })()"""
    send("Runtime.evaluate", {"expression": expr1, "returnByValue": True})
    r1 = recv_until(lambda m: m.get("id") and m["id"]==msg_id["n"] and m.get("result"))
    # 2) 查找全局签名/请求客户端
    expr2 = """(() => {
      const keys = Object.keys(window).filter(k=>/sign|bogus|token|request|axios|http|api|fetch|msToken|music/i.test(k));
      // 试着找能发请求的函数
      const probes = {};
      try { probes.hasMSign = typeof window._mstandard_sign_request } catch(e){}
      try { probes.webmssdk = typeof window.webmssdk } catch(e){}
      return {keys: keys.slice(0,60), probes};
    })()"""
    send("Runtime.evaluate", {"expression": expr2, "returnByValue": True})
    r2 = recv_until(lambda m: m.get("id") and m["id"]==msg_id["n"] and m.get("result"))
    out = {}
    if r1 and r1.get("result",{}).get("result",{}).get("value"):
        out["dom"] = r1["result"]["result"]["value"]
    if r2 and r2.get("result",{}).get("result",{}).get("value"):
        out["globals"] = r2["result"]["result"]["value"]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ws.close()

if __name__ == "__main__":
    main()
