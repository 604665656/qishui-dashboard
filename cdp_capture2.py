"""CDP 接管本机已登录 Edge（localhost:9222）。
抓取给定 URL 下的「请求 URL」与「响应 body」，重点找出创作者后台的数据 API。
改进点：
 - 启用 Network 后立即 enable，再 navigate（避免漏接）
 - 同时记录 requestWillBeSent（拿到所有请求 URL，含 API 路径与 query）
 - 对 responseReceived 用 loadingFinished 触发 getResponseBody，处理 base64
 - 打印所有非静态资源的请求/响应 URL，便于定位 API
"""
import json, os, sys, time, urllib.request, urllib.parse
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222
BASE = f"http://127.0.0.1:{PORT}"

reqs = {}     # requestId -> {url, method, type}
bodies = {}   # requestId -> body string
pending = {}  # msg_id -> requestId
msg_id = {"n": 0}
ws = None


def http_get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())


def send(method, params=None):
    msg_id["n"] += 1
    i = msg_id["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    return i


def main():
    global ws
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://music.douyin.com/console/statistics?metricType=6&enter_from=home_data_center"
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    if tab:
        ws_url = tab["webSocketDebuggerUrl"]
        print("复用标签:", tab.get("url"))
    else:
        newt = http_get("/json/new?" + urllib.parse.quote(url, safe=":"))
        ws_url = newt["webSocketDebuggerUrl"]
        print("新建标签:", url)

    ws = create_connection(ws_url, timeout=60)
    send("Network.enable", {"maxPostDataSize": 0})
    send("Page.enable")
    time.sleep(0.5)
    send("Page.navigate", {"url": url})
    time.sleep(1.0)

    stop = time.time() + wait
    while time.time() < stop:
        try:
            raw = ws.recv()
        except Exception:
            break
        try:
            m = json.loads(raw)
        except Exception:
            continue
        method = m.get("method")
        mid = m.get("id")
        if method == "Network.requestWillBeSent":
            p = m["params"]
            rid = p["requestId"]
            reqs[rid] = {"url": p["request"].get("url", ""),
                          "method": p["request"].get("method", ""),
                          "resourceType": p.get("resourceType", "")}
        elif method == "Network.responseReceived":
            rid = m["params"]["requestId"]
            resp = m["params"].get("response", {})
            reqs.setdefault(rid, {})["url"] = resp.get("url", "")
            reqs.setdefault(rid, {})["mime"] = resp.get("mimeType", "")
            reqs.setdefault(rid, {})["status"] = resp.get("status", "")
        elif method == "Network.loadingFinished":
            rid = m["params"]["requestId"]
            i = send("Network.getResponseBody", {"requestId": rid})
            pending[i] = rid
        elif mid in pending:
            rid = pending.pop(mid)
            res = m.get("result", {})
            body = res.get("body", "") or ""
            if res.get("base64Encoded") and body:
                try:
                    import base64
                    body = base64.b64decode(body).decode("utf-8", "ignore")
                except Exception:
                    pass
            bodies[rid] = body
        time.sleep(0.01)

    # 汇总
    out = []
    for rid, r in reqs.items():
        u = r.get("url", "")
        b = bodies.get(rid, "")
        entry = {"url": u, "method": r.get("method", ""), "mime": r.get("mime", ""),
                 "status": r.get("status", ""), "size": len(b)}
        try:
            entry["json"] = json.loads(b or "{}")
        except Exception:
            if b:
                entry["raw"] = b[:800]
        out.append(entry)

    json.dump(out, open("cdp_capture2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 打印所有像 API 的请求（过滤静态资源）
    STATIC = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".ttf", ".ico", ".map")
    print("\n=== 捕获", len(out), "个请求 ===")
    api_hits = 0
    for r in out:
        u = r.get("url", "")
        low = u.lower()
        if any(u.endswith(s) for s in STATIC):
            continue
        if any(k in low for k in ("api", "song", "statistic", "metric", "track", "creator", "console", "list", "data", "luna", "aweme", "play", "collect", "comment", "like")):
            api_hits += 1
            print(f"  [{r.get('status')}] {r.get('size'):>7}  {r.get('method'):<4} {u}")
    print("API 候选:", api_hits)
    ws.close()


if __name__ == "__main__":
    main()
