"""捕获单曲详情页网络 + 探测列表页 DOM（分页/页大小/指标tab）。"""
import json, os, sys, time, urllib.request, urllib.parse
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222
BASE = f"http://127.0.0.1:{PORT}"
resp_capture = {}
pending = {}
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
    url = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 18
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    if not tab:
        newt = http_get("/json/new?" + urllib.parse.quote(url, safe=":"))
        ws_url = newt["webSocketDebuggerUrl"]
    else:
        ws_url = tab["webSocketDebuggerUrl"]
        # 让该标签导航到目标 URL
    ws = create_connection(ws_url, timeout=60)
    send("Network.enable", {"maxPostDataSize": 0})
    send("Page.enable")
    time.sleep(0.4)
    send("Page.navigate", {"url": url})
    time.sleep(1.2)

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
        method = m.get("method"); mid = m.get("id")
        if method == "Network.responseReceived":
            rid = m["params"]["requestId"]
            u = m["params"].get("response", {}).get("url", "")
            resp_capture.setdefault(rid, {})["url"] = u
            resp_capture[rid]["mime"] = m["params"].get("response", {}).get("mimeType", "")
        elif method == "Network.loadingFinished":
            rid = m["params"]["requestId"]
            pending[send("Network.getResponseBody", {"requestId": rid})] = rid
        elif mid in pending:
            rid = pending.pop(mid)
            res = m.get("result", {})
            body = res.get("body", "") or ""
            if res.get("base64Encoded") and body:
                import base64
                body = base64.b64decode(body).decode("utf-8", "ignore")
            resp_capture[rid]["body"] = body
        time.sleep(0.01)

    # 保存所有 disclosure 与 song 相关响应
    out = []
    for rid, v in resp_capture.items():
        u = v.get("url", "")
        if "api/" in u:
            b = v.get("body", "")
            item = {"url": u, "mime": v.get("mime", ""), "size": len(b)}
            try:
                item["json"] = json.loads(b or "{}")
            except Exception:
                if b: item["raw"] = b[:600]
            out.append(item)
    json.dump(out, open("cdp_detail.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("=== 捕获", len(out), "个 api 响应 ===")
    for r in out:
        print(f"  [{r.get('size'):>7}] {r.get('url')}")
        if "json" in r and "songs" in str(r["url"]):
            print("     keys:", list(r.get("json",{}).get("data",{}).keys()))
    ws.close()

if __name__ == "__main__":
    main()
