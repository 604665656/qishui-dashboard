"""从浏览器提取 music.douyin.com / douyin.com 的 cookie，供 Python 直接调用未签名接口。"""
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
def recv_id(i, timeout=20):
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
    # 新建一个空白标签专门用于取 cookie
    newt = http_get("/json/new?about:blank")
    ws = create_connection(newt["webSocketDebuggerUrl"], timeout=30)
    send("Network.enable")
    time.sleep(0.5)
    send("Network.getCookies", {"urls": ["https://music.douyin.com", "https://www.douyin.com",
                                          "https://douyin.com", "https://music.douyin.com/"]})
    m = recv_id(MSG["n"], timeout=15)
    cookies = (m.get("result", {}).get("cookies", []) if m else [])
    out = {c["name"]: c["value"] for c in cookies}
    json.dump(out, open("cookies.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"提取 cookie 数: {len(out)}")
    # 打印关键 cookie 名（不打印值）
    print("names:", list(out.keys()))
    ws.close()

if __name__ == "__main__":
    main()
