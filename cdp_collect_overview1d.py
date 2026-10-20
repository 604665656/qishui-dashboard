"""采集每首歌 disclosure/overview 的 period=1（近1天=最新一日）指标，得到昨日汽水播放量(mt2)与汽水热度指数(mt1)。
未签名接口，批量 Promise.all。保存 overview_1d.json，并记录数据日期(updateTime→北京日期)。
"""
import json, os, sys, time, urllib.request, datetime
from websocket import create_connection

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PORT = 9222; BASE = f"http://127.0.0.1:{PORT}"; MSG = {"n": 0}; ws = None
OUT = "overview_1d.json"

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
        return d.get("metrics", {}), set(d.get("done", [])), d.get("date")
    return {}, set(), None

def save(metrics, done, date):
    json.dump({"date": date, "done": sorted(done), "metrics": metrics},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def main():
    global ws
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ids = load_ids()
    metrics, done, date = load_done()
    tabs = http_get("/json")
    tab = next((t for t in tabs if "music.douyin" in t.get("url", "")), None)
    ws = create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    send("Runtime.enable"); time.sleep(0.3)
    todo = [i for i in ids if i not in done]
    print(f"总 {len(ids)}，已完成 {len(done)}，待采 {len(todo)}", flush=True)
    for start in range(0, len(todo), batch):
        chunk = todo[start:start+batch]
        ids_json = json.dumps(chunk)
        expr = """(async () => {
          const ids = %s;
          const results = {}; let ut = null;
          await Promise.all(ids.map(async (id) => {
            try {
              const r = await fetch('https://music.douyin.com/api/statistics/disclosure/overview?scope=2&songID='+id+'&period=1', {credentials:'include'});
              const t = await r.text();
              let j; try{j=JSON.parse(t);}catch(e){return;}
              if (j && j.baseResp && j.baseResp.errorCode===0 && j.data && j.data.metrics) {
                const m = {}; for (const x of j.data.metrics) m[x.metricType] = x.value;
                results[id] = {m:m, ut:j.data.updateTime};
                if (j.data.updateTime) ut = j.data.updateTime;
              }
            } catch(e){}
          }));
          return {results, ut};
        })()""" % ids_json
        ok = False
        for attempt in range(4):
            send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            m = recv_id(MSG["n"], timeout=35)
            res = (m.get("result", {}).get("result", {}).get("value") if m else None)
            if res and isinstance(res, dict) and res.get("results"):
                for k, v in res["results"].items():
                    metrics[k] = v["m"]; done.add(k)
                    if v.get("ut"): date = v["ut"]
                save(metrics, done, date)
                print(f"batch {start//batch+1} ok | +{len(res['results'])} | 累计 {len(done)}", flush=True)
                ok = True
                break
            else:
                print(f"batch {start//batch+1} attempt {attempt+1} fail: {json.dumps(res)[:120]}", flush=True)
                time.sleep(1.5*(attempt+1))
        if not ok:
            print(f"!!! batch {start//batch+1} 放弃", flush=True)
        time.sleep(0.3)
    # 日期：updateTime(秒,UTC) -> 北京日期
    bj = None
    if date:
        bj = (datetime.datetime.utcfromtimestamp(int(date)) + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    print(f"完成 period=1：{len(done)} 首 | 数据日期(updateTime)={date} 北京={bj}", flush=True)
    ws.close()

if __name__ == "__main__":
    main()
