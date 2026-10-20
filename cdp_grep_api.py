"""进入已登录页面，收集所有 script src，逐一 fetch 并搜索 API 路径与指标关键字。"""
import json, os, sys, time, urllib.request
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
BASE = "http://127.0.0.1:9222"


def http_get(p):
    return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())


def main():
    tabs = [t for t in http_get("/json") if t.get("type") == "page" and "music.douyin" in t.get("url", "")]
    if not tabs:
        tabs = [t for t in http_get("/json") if t.get("type") == "page"]
    tab = tabs[0]
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=40); ws.settimeout(40)

    def cmd(m, p=None, i=[0]):
        i[0] += 1; ws.send(json.dumps({"id": i[0], "method": m, "params": p or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == i[0]:
                return r

    cmd("Page.enable"); cmd("Runtime.enable")
    js = """
    (async () => {
      const srcs = [...document.querySelectorAll('script[src]')].map(s=>s.src).filter(u=>/\\.js/.test(u));
      const found = [];
      for (const u of srcs.slice(0,40)) {
        try {
          const t = await (await fetch(u)).text();
          const paths = [...t.matchAll(/\\/api\\/v1\\/[A-Za-z0-9_\\/-]+/g)].map(x=>x[0]);
          const keys = [...t.matchAll(/(songs?|song_list|statistic|data_center|play_count|like|collect|comment|hot|revenue|track)[A-Za-z0-9_]*\\b/gi)].map(x=>x[0]);
          if (paths.length || keys.length) found.push({u:u.split('/').pop(), paths:[...new Set(paths)].slice(0,30), keys:[...new Set(keys)].slice(0,40)});
        } catch(e){}
      }
      return found;
    })()
    """
    r = cmd("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
    val = r.get("result", {}).get("result", {}).get("value") or []
    print("发现", len(val), "个含 API 的 chunk")
    for f in val:
        print("\n== chunk:", f["u"])
        print("  paths:", f["paths"][:30])
        print("  keys:", f["keys"][:40])
    ws.close()


if __name__ == "__main__":
    main()
