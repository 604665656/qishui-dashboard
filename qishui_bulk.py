"""全量下载：读取 catalog.json，并发抓取每首曲目的音频直链 + 歌词，支持断点续传。"""
import json, os, re, sys, threading, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TRACK = "https://music.douyin.com/qishui/share/track?track_id={tid}"
ROOT = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(ROOT, "音乐")
LYRIC = os.path.join(ROOT, "歌词")
PLAIN = os.path.join(ROOT, "歌词_纯文本")
STATE = os.path.join(ROOT, "state.json")
for d in (AUDIO, LYRIC, PLAIN):
    os.makedirs(d, exist_ok=True)

lock = threading.Lock()
state = {}
if os.path.exists(STATE):
    state = json.load(open(STATE, encoding="utf-8"))

stat = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0}
t0 = time.time()


def safe(name, maxlen=60):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (name or "").strip())
    return (s[:maxlen] or "untitled")


def fmt(ms):
    ms = int(round(float(ms or 0)))
    m, s = divmod(ms, 60000)
    return f"{m:02d}:{s // 1000:02d}.{(s % 1000) // 10:02d}"


def to_lrc(lyrics):
    if not lyrics:
        return ""
    return "\n".join(
        f"[{fmt(s.get('startMs', 0))}]{(s.get('text') or '').strip()}"
        for s in lyrics.get("sentences", [])
        if (s.get("text") or "").strip()
    ) + "\n"


def http(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://music.douyin.com/"})
    return urllib.request.urlopen(req, timeout=timeout)


def work(args):
    idx, tid, name = args
    base = f"{idx:04d}-{safe(name)}"
    if state.get(tid, {}).get("ok"):
        with lock:
            stat["skip"] += 1
        return
    try:
        h, i = "", -1
        k = "_ROUTER_DATA = "
        for attempt in range(5):
            try:
                h = http(TRACK.format(tid=tid), 40).read().decode("utf-8", "ignore")
            except Exception:
                h = ""
            i = h.find(k)
            if i >= 0:
                break
            time.sleep(1.2 * (attempt + 1))
        if i < 0:
            raise RuntimeError("no SSR")
        d, _ = json.JSONDecoder().raw_decode(h[i + len(k):])
        a = (d.get("loaderData", {}).get("track_page", {}) or {}).get("audioWithLyricsOption")
        if not a:
            raise RuntimeError("no option")

        title = a.get("trackName") or name or tid
        base = f"{idx:04d}-{safe(title)}"
        rec = {"title": title, "artist": a.get("artistName"),
               "track_id": tid, "duration": a.get("duration"),
               "file": base, "ok": False}

        url = a.get("url")
        n = 0
        if url:
            p = os.path.join(AUDIO, base + ".m4a")
            with http(url, 180) as r, open(p, "wb") as f:
                while True:
                    c = r.read(131072)
                    if not c:
                        break
                    f.write(c)
                    n += len(c)
                if n < 8192:
                    raise RuntimeError("audio too small")

        lrc = to_lrc(a.get("lyrics"))
        if lrc:
            open(os.path.join(LYRIC, base + ".lrc"), "w", encoding="utf-8").write(lrc)
            open(os.path.join(PLAIN, base + ".txt"), "w", encoding="utf-8").write(
                "\n".join(l.split("]", 1)[1] for l in lrc.strip().split("\n")) + "\n")

        rec["ok"] = True
        rec["bytes"] = n
        with lock:
            state[tid] = rec
            stat["ok"] += 1
            stat["bytes"] += n
    except Exception as e:
        with lock:
            state[tid] = {"track_id": tid, "title": name, "ok": False, "err": str(e)[:120]}
            stat["fail"] += 1
    with lock:
        done = stat["ok"] + stat["fail"] + stat["skip"]
        if done % 25 == 0:
            el = time.time() - t0
            print(f"进度 {done}/{TOTAL} | ok={stat['ok']} fail={stat['fail']} "
                  f"skip={stat['skip']} | {stat['bytes']/1048576:.0f} MB | "
                  f"{el/60:.1f} min", flush=True)
            json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)


def main():
    global TOTAL
    catalog = json.load(open(os.path.join(ROOT, "catalog.json"), encoding="utf-8"))
    items = [(i, t, n) for i, (t, n) in enumerate(catalog.items(), 1)]
    TOTAL = len(items)
    print(f"开始全量抓取：{TOTAL} 首，并发 10", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, items))
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    idx = [v for v in state.values() if v.get("ok")]
    idx.sort(key=lambda r: r.get("file", ""))
    json.dump(idx, open(os.path.join(ROOT, "曲库索引.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n完成 ok={stat['ok']} fail={stat['fail']} skip={stat['skip']} "
          f"| {stat['bytes']/1073741824:.2f} GB | {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
