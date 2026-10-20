"""通过页面内 fetch（带 cookie + 固定 a_bogus）翻页拉取 disclosure/songs 全量列表。
a_bogus 对 currentPage 不敏感，可改页码复用；pageSize 敏感，固定为 10。
增量保存 stats_list.json，断点续传。"""
import json, os, sys, time, urllib.request
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222
BASE = f"http://127.0.0.1:{PORT}"
MSG = {"n": 0}
ws = None
OUT = "stats_list.json"
MS = "opmYjVGD9mKqwIdtbfhEW7jtEmBOpx-Mxqks-NUS0X2orWsxt2UUS0hAJsRbpLJbEZmcVxPg7C0nseaV3oIcqevdh4C9q6ZJVUxzOPJv4xq2BHPoAW_AL0j04mBfEyQ_-YOzKfmWjEB4D0YlhZKshz1K0NhvCrRVZm8kGqelqt7Yh1xtA1BMJ4cZ"
AB = "O7snkwt7xZRcPplS8Kayt7OUtZoMNTuyKFidSY7YtxxRyHMGloM9zNb8rxwcsgVDmSpHoq3HgV0lYxxcqfiip%2FnpomkDu2iy%2FGnIISfLMqN2GekdENjxeu0zK7%2FH0CsYmQc1i%2FvR6sMqZVVAIr9uWpVHF%2FUxQQbDMrVH-p0oipNIgBkS78Y%3D"

def http_get(p):
    return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())

def send(method, params=None):
    MSG["n"] += 1
    i = MSG["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    return i

def recv_id(i, timeout=40):
    stop = time.time() + timeout
    while time.time() < stop:
        try: raw = ws.recv()
        except Exception: break
        try: m = json.loads(raw)
        except Exception: continue
        if m.get("id") == i: return m
    return None

def load_done():
    if os.path.exists(OUT):
        d = json.load(open(OUT, encoding="utf-8"))
        return d.get("songs", []), set(d.get("done_pages", []))
    return [], set()

def save(songs, done_pages, total=None):
    json.dump({"total": total, "done_pages": sorted(done_pages),
               "songs": songs}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

def main():
    global ws
    start_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end_page = int(sys.argv[2]) if len(sys.argv) > 2 else 326
    songs, done = load_done()
    by_id = {s["metaSongId"]: s for s in songs}
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable")
    time.sleep(0.3)
    total = None
    for page in range(start_page, end_page + 1):
        if page in done:
            continue
        ok = False
        for attempt in range(5):
            url = (f"https://music.douyin.com/api/statistics/disclosure/songs"
                   f"?songType=1&songForm=1&currentPage={page}&pageSize=10"
                   f"&msToken={MS}&a_bogus={AB}")
            expr = """(async () => {
              try {
                const r = await fetch(%r, {credentials:'include'});
                const t = await r.text();
                let j; try{j=JSON.parse(t);}catch(e){return {status:r.status, err:'json', head:t.slice(0,120)};}
                return {status:r.status, data:(j.data||null), base:(j.baseResp||null)};
              } catch(e){ return {err:String(e)}; }
            })()""" % url
            send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            m = recv_id(MSG["n"], timeout=35)
            res = (m.get("result", {}).get("result", {}).get("value") if m else None)
            if res and res.get("status") == 200 and res.get("data") and res["data"].get("songs"):
                d = res["data"]
                total = d.get("total")
                for s in d["songs"]:
                    by_id[s["metaSongId"]] = s
                done.add(page)
                songs = list(by_id.values())
                save(songs, done, total)
                print(f"page {page} ok | total={total} | 已收 {len(songs)}", flush=True)
                ok = True
                break
            else:
                print(f"page {page} attempt {attempt+1} fail: {json.dumps(res)[:160]}", flush=True)
                time.sleep(1.5 * (attempt + 1))
        if not ok:
            print(f"!!! page {page} 放弃（5次失败）", flush=True)
        time.sleep(0.4)
    print(f"完成：共 {len(songs)} 首，done_pages={len(done)}", flush=True)
    ws.close()

if __name__ == "__main__":
    main()
