"""批量采集每首歌的 disclosure/overview（未签名接口），得到 8 个 7日指标。
用 Promise.all 每批并发若干首，按 songID 对齐。增量保存 overview_stats.json。
用法：python cdp_collect_overview.py [batch=20] [max_workers_concurrent=20]
songID 来源：stats_list.json（列表已收的 metaSongId）。
"""
import json, os, sys, time, urllib.request
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222; BASE = f"http://127.0.0.1:{PORT}"; MSG = {"n": 0}; ws = None
OUT = "overview_stats.json"

def http_get(p): return json.loads(urllib.request.urlopen(BASE + p, timeout=10).read())
def send(method, params=None):
    MSG["n"] += 1; i = MSG["n"]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}})); return i
def recv_id(i, timeout=40):
    stop = time.time() + timeout
    while time.time() < stop:
        try: raw = ws.recv()
        except Exception: break
        try: m = json.loads(raw)
        except Exception: continue
        if m.get("id") == i: return m
    return None

def load_ids():
    d = json.load(open("stats_list.json", encoding="utf-8"))
    return [s["metaSongId"] for s in d.get("songs", [])]

def load_done():
    if os.path.exists(OUT):
        d = json.load(open(OUT, encoding="utf-8"))
        return d.get("metrics", {}), set(d.get("done", []))
    return {}, set()

def save(metrics, done):
    json.dump({"done": sorted(done), "metrics": metrics}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

def main():
    global ws
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ids = load_ids()
    metrics, done = load_done()
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.3)
    todo = [i for i in ids if i not in done]
    print(f"总 {len(ids)} 首，已完成 {len(done)}，待采 {len(todo)}", flush=True)
    for start in range(0, len(todo), batch):
        chunk = todo[start:start+batch]
        ids_json = json.dumps(chunk)
        expr = """(async () => {
          const ids = %s;
          const results = {};
          await Promise.all(ids.map(async (id) => {
            try {
              const r = await fetch('https://music.douyin.com/api/statistics/disclosure/overview?scope=2&songID='+id+'&period=2', {credentials:'include'});
              const t = await r.text();
              let j; try{j=JSON.parse(t);}catch(e){return;}
              if (j && j.baseResp && j.baseResp.errorCode===0 && j.data && j.data.metrics) {
                const m = {};
                for (const x of j.data.metrics) m[x.metricType] = x.value;
                results[id] = m;
              }
            } catch(e){}
          }));
          return results;
        })()""" % ids_json
        ok = False
        for attempt in range(4):
            send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            m = recv_id(MSG["n"], timeout=35)
            res = (m.get("result", {}).get("result", {}).get("value") if m else None)
            if res and isinstance(res, dict) and len(res) > 0:
                for k, v in res.items():
                    metrics[k] = v; done.add(k)
                save(metrics, done)
                print(f"batch {start//batch+1} ok | +{len(res)} | 累计 {len(done)}", flush=True)
                ok = True
                break
            else:
                print(f"batch {start//batch+1} attempt {attempt+1} fail: {json.dumps(res)[:120]}", flush=True)
                time.sleep(1.5*(attempt+1))
        if not ok:
            print(f"!!! batch {start//batch+1} 放弃", flush=True)
        time.sleep(0.3)
    print(f"完成 overview：共 {len(done)} 首有数据", flush=True)
    ws.close()

if __name__ == "__main__":
    main()
