# -*- coding: utf-8 -*-
import json, os, sys, time, datetime, urllib.request, urllib.error
PORT = 9222
CDP_HTTP = f"http://127.0.0.1:{PORT}"
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

def http_get_json(path):
    return json.loads(urllib.request.urlopen(CDP_HTTP + path, timeout=10).read())

def get_cookies():
    ws_url = http_get_json("/json/version").get("webSocketDebuggerUrl")
    from websocket import create_connection
    tabs = http_get_json("/json")
    page = next((t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
    ws = create_connection(page["webSocketDebuggerUrl"], timeout=30)
    n = [0]
    def send(m, p=None):
        n[0] += 1; i = n[0]; ws.send(json.dumps({"id": i, "method": m, "params": p or {}})); return i
    def recvid(i, t=20):
        e = time.time()
        while time.time() - e < t:
            try: r = json.loads(ws.recv())
            except Exception: return None
            if r.get("id") == i: return r
    send("Network.enable"); time.sleep(0.3)
    r = recvid(send("Network.getAllCookies"), 15)
    ws.close()
    cookies = (r.get("result", {}).get("cookies", [])) if r else []
    ck = "; ".join(f"{c['name']}={c['value']}" for c in cookies
                   if "douyin" in c.get("domain", "") or "bytedance" in c.get("domain", ""))
    return ck, {c["name"]: c["value"] for c in cookies}

def py_get(url, cookies, is_json=True, timeout=25):
    req = urllib.request.Request(url, headers={
        "Cookie": cookies, "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.douyin.com/console/song/index"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        txt = resp.read().decode("utf-8", "replace")
    return json.loads(txt) if is_json else txt

ck, ckmap = get_cookies()
print("cookie len:", len(ck))
msToken = ckmap.get("msToken", "")
print("msToken present:", bool(msToken))

BASE = "https://music.douyin.com/api/statistics/disclosure/songs"
combos = {
    "A_no_sig": f"{BASE}?songType=1&songForm=1&currentPage=1&pageSize=10",
    "B_empty_sig": f"{BASE}?songType=1&songForm=1&currentPage=1&pageSize=10&msToken={msToken}&a_bogus=",
    "C_msToken_only": f"{BASE}?songType=1&songForm=1&currentPage=1&pageSize=10&msToken={msToken}",
}
for name, url in combos.items():
    try:
        j = py_get(url, ck, timeout=20)
        songs = j.get("data", {}).get("songs", [])
        total = j.get("data", {}).get("total")
        code = j.get("baseResp", {}).get("errorCode")
        print(f"[{name}] code={code} total={total} songs_returned={len(songs)}")
        if songs:
            print("   sample:", json.dumps(songs[0], ensure_ascii=False)[:200])
    except Exception as e:
        print(f"[{name}] EXCEPTION: {e}")
