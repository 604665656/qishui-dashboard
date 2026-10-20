"""测试：在页面上下文里用改了 currentPage 的同一签名 URL 发 fetch，看 a_bogus 是否绑定页码。"""
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
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable")
    time.sleep(0.3)
    base = ("https://music.douyin.com/api/statistics/disclosure/songs"
            "?songType=1&songForm=1&currentPage=__PAGE__&pageSize=10"
            "&msToken=opmYjVGD9mKqwIdtbfhEW7jtEmBOpx-Mxqks-NUS0X2orWsxt2UUS0hAJsRbpLJbEZmcVxPg7C0nseaV3oIcqevdh4C9q6ZJVUxzOPJv4xq2BHPoAW_AL0j04mBfEyQ_-YOzKfmWjEB4D0YlhZKshz1K0NhvCrRVZm8kGqelqt7Yh1xtA1BMJ4cZ"
            "&a_bogus=O7snkwt7xZRcPplS8Kayt7OUtZoMNTuyKFidSY7YtxxRyHMGloM9zNb8rxwcsgVDmSpHoq3HgV0lYxxcqfiip%2FnpomkDu2iy%2FGnIISfLMqN2GekdENjxeu0zK7%2FH0CsYmQc1i%2FvR6sMqZVVAIr9uWpVHF%2FUxQQbDMrVH-p0oipNIgBkS78Y%3D")
    for page in (1, 2, 3):
        url = base.replace("__PAGE__", str(page))
        expr = """(async () => {
          try {
            const r = await fetch(%r, {credentials:'include'});
            const t = await r.text();
            let j; try{j=JSON.parse(t);}catch(e){return {status:r.status, err:'not json', head:t.slice(0,200)};}
            const songs = (j.data&&j.data.songs)||[];
            return {status:r.status, total:(j.data&&j.data.total), count:songs.length,
                    first:(songs[0]&&songs[0].metaSongId), last:(songs[songs.length-1]&&songs[songs.length-1].metaSongId)};
          } catch(e){ return {err:String(e)}; }
        })()""" % url
        send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        m = recv_id(msg_id["n"], timeout=25)
        res = m.get("result", {}).get("result", {}).get("value") if m else None
        print(f"page={page} -> {json.dumps(res, ensure_ascii=False)}")
        time.sleep(1)
    # 测试改变 pageSize 是否也生效
    for ps in (50, 100, 200):
        url = base.replace("__PAGE__", "1").replace("pageSize=10", f"pageSize={ps}")
        expr = """(async () => {
          try {
            const r = await fetch(%r, {credentials:'include'});
            const t = await r.text();
            let j; try{j=JSON.parse(t);}catch(e){return {status:r.status, err:'not json', head:t.slice(0,200)};}
            const songs = (j.data&&j.data.songs)||[];
            return {status:r.status, total:(j.data&&j.data.total), count:songs.length};
          } catch(e){ return {err:String(e)}; }
        })()""" % url
        send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        m = recv_id(msg_id["n"], timeout=25)
        res = m.get("result", {}).get("result", {}).get("value") if m else None
        print(f"pageSize={ps} -> {json.dumps(res, ensure_ascii=False)}")
        time.sleep(1)
    ws.close()

if __name__ == "__main__":
    main()
