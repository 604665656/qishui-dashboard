# -*- coding: utf-8 -*-
"""对【当前活着的】CDP 浏览器会话做结算接口诊断。"""
import json, sys, time, urllib.request, urllib.error
try:
    from websocket import create_connection
except Exception as e:
    print("websocket-client 未安装:", e); sys.exit(2)

CDP_HTTP = "http://127.0.0.1:9222"
SETTLE_API = "https://music.douyin.com/console/api/v1/settlement/statement"

def http_json(path):
    return json.loads(urllib.request.urlopen(CDP_HTTP + path, timeout=10).read())

def get_cookies():
    try:
        ver = http_json("/json/version")
        ws_url = ver.get("webSocketDebuggerUrl")
    except Exception:
        ws_url = None
    if not ws_url:
        try:
            tabs = http_json("/json")
            ws_url = tabs[0].get("webSocketDebuggerUrl") if tabs else None
        except Exception:
            return None, {}
    tabs = http_json("/json")
    page = next((t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
    if not page:
        return None, {}
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
    ckm = {c["name"]: c["value"] for c in cookies}
    return (ck or None), ckm, cookies

def py_get(url, cookies, is_json=True, timeout=25):
    req = urllib.request.Request(url, headers={
        "Cookie": cookies, "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.douyin.com/console/settlement/index"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        txt = resp.read().decode("utf-8", "replace")
    return json.loads(txt) if is_json else txt

print("=== 1) 探测 CDP 9222 ===")
try:
    ver = http_json("/json/version")
    print("9222 在线:", ver.get("Browser"), "|", ver.get("webSocketDebuggerUrl") and "有ws")
except Exception as e:
    print("9222 离线/不可达:", e)
    print("  → CDP 浏览器未运行。请先用 汽水数据更新.exe 的登录功能，或命令行 --login 拉起专用 Edge 并登录。")
    sys.exit(1)

ck, ckm, cookies = get_cookies()
print("\n=== 2) Cookie 概览 ===")
print("douyin/bytedance Cookie 串长度:", len(ck) if ck else 0)
doms = {}
for c in cookies:
    d = c.get("domain", "?")
    doms[d] = doms.get(d, 0) + 1
print("域分布(仅域名/计数):")
for d, n in sorted(doms.items()):
    print("   ", d, n)
uid = ckm.get("uid_tt_ss") or ckm.get("uid_tt") or ""
print("uid_tt_ss/uid_tt 是否存在:", bool(uid), "| uid=", (uid[:10] + "…") if uid else "(空)")
sess = [k for k in ckm if any(x in k.lower() for x in ("session", "sid", "ticket", "token", "passport", "ssid", "uid_tt"))]
print("疑似会话/身份 Cookie:", sess[:15])

if not ck:
    print("\n✗ 没有取到任何 douyin/bytedance Cookie —— 专用 Edge 并未登录。请先在 CDP Edge(端口9222/user-data-dir=C:\\edge-cdp)里登录创作者后台。")
    sys.exit(0)

print("\n=== 3) 结算月份 period_range ===")
try:
    pr = py_get(f"{SETTLE_API}/period_range", ck)
    print("HTTP 返回:", json.dumps(pr, ensure_ascii=False)[:600])
    data = pr.get("data", {}) or {}
    sp, ep = data.get("startPeriod"), data.get("endPeriod")
    if sp and ep:
        print(f"✓ 发现已结算区间: {sp} → {ep}")
    else:
        print("✗ period_range 没有返回月份（data 为空或字段缺失）。")
        # 备选路径
        for alt in ("/api/v1/settlement/statement/period_range",
                    "https://music.douyin.com/console/api/settlement/statement/period_range"):
            try:
                a = py_get(alt, ck)
                print("  备选", alt, "→", json.dumps(a, ensure_ascii=False)[:300])
            except Exception as ee:
                print("  备选", alt, "ERR", str(ee)[:120])
except Exception as e:
    print("period_range 调用异常:", e)

print("\n=== 4) 直接用 download 试一个月(若有区间) ===")
try:
    pr = py_get(f"{SETTLE_API}/period_range", ck)
    data = pr.get("data", {}) or {}
    sp = data.get("startPeriod")
    if sp:
        j = py_get(f"{SETTLE_API}/download?time={sp}", ck)
        print("download", sp, "→", json.dumps(j, ensure_ascii=False)[:300])
    else:
        print("无区间可试。")
except Exception as e:
    print("download 异常:", e)
