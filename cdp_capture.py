"""CDP 接管本机已登录 Edge（localhost:9222），抓某 URL 下的网络响应。单线程 recv，避免抢消息。"""
import json, os, sys, time, urllib.request, threading
from websocket import create_connection

# 关键：绕开环境代理，直连 localhost
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222
BASE = f"http://127.0.0.1:{PORT}"
import urllib.parse

bodies = {}            # requestId -> {url, body}
pending = {}           # 自增id -> requestId (等待 getResponseBody 结果)
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
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    ver = http_get("/json/version")
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    if tab:
        ws_url = tab["webSocketDebuggerUrl"]
        print("复用标签:", tab.get("url"))
    else:
        newt = http_get("/json/new?" + urllib.parse.quote(url, safe=":"))
        ws_url = newt["webSocketDebuggerUrl"]
        print("新建标签:", url)

    ws = create_connection(ws_url, timeout=40)
    send("Network.enable")
    send("Page.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": url})
    time.sleep(0.8)

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
        if method == "Network.responseReceived":
            rid = m["params"]["requestId"]
            bodies.setdefault(rid, {"url": m["params"].get("response", {}).get("url", ""),
                                    "mime": m["params"].get("response", {}).get("mimeType", ""),
                                    "body": None})
        elif method == "Network.loadingFinished":
            rid = m["params"]["requestId"]
            i = send("Network.getResponseBody", {"requestId": rid})
            pending[i] = rid
        elif mid in pending:
            rid = pending.pop(mid)
            rb = m.get("result", {}).get("body", "")
            bodies[rid]["body"] = rb if isinstance(rb, str) else ""
        time.sleep(0.02)

    out = []
    for rid, v in bodies.items():
        entry = {"requestId": rid, "url": v["url"], "mime": v["mime"],
                 "size": len(v["body"] or "")}
        try:
            entry["json"] = json.loads(v["body"] or "{}")
        except Exception:
            entry["raw"] = (v["body"] or "")[:500]
        out.append(entry)
    json.dump(out, open("cdp_capture.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n捕获", len(out), "个响应（存 cdp_capture.json）")
    for r in out:
        u = (r.get("url") or "")
        if any(k in u.lower() for k in ("song", "statistic", "metric", "data", "list", "luna", "track", "creator", "console")):
            print("  ★", r.get("size"), r.get("mime"), u)
    ws.close()


if __name__ == "__main__":
    main()
