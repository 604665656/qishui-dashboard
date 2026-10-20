"""CDP 操作：导航到指定 URL 并执行 JS，打印结果。"""
import json, os, sys, time, urllib.request
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

BASE = "http://127.0.0.1:9222"


def http_get(p):
    return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "about:blank"
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 6
    js = sys.argv[3] if len(sys.argv) > 3 else "document.title + ' || ' + document.body.innerText.slice(0,600)"

    tabs = [t for t in http_get("/json") if t.get("type") == "page"]
    tab = tabs[0] if tabs else None
    if not tab:
        tab = http_get("/json/new?about:blank")
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    ws.settimeout(30)

    def cmd(method, params=None, wid=1):
        ws.send(json.dumps({"id": wid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == wid:
                return m

    cmd("Page.enable", wid=1)
    cmd("Runtime.enable", wid=2)
    cmd("Page.navigate", {"url": url}, wid=3)
    time.sleep(wait)
    r = cmd("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True}, wid=4)
    val = r.get("result", {}).get("result", {}).get("value")
    print(json.dumps(val, ensure_ascii=False, indent=1)[:3000] if not isinstance(val, str) else val[:3000])
    ws.close()


if __name__ == "__main__":
    main()
