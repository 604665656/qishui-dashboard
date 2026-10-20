"""BFS 扩张：从种子曲目出发，通过每首曲目页的 artistTracks 收集该音乐人全部 track_id。"""
import json, sys, time, threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TRACK = "https://music.douyin.com/qishui/share/track?track_id={tid}"
ARTIST_ID = "7626025942168160282"
ARTIST = "许许许许许丶若辰"

lock = threading.Lock()
catalog = {}       # tid -> name
fail = []


def fetch(tid):
    for _ in range(2):
        try:
            req = urllib.request.Request(TRACK.format(tid=tid),
                                         headers={"User-Agent": UA,
                                                  "Referer": "https://music.douyin.com/"})
            h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
            k = "_ROUTER_DATA = "
            i = h.find(k)
            if i < 0:
                return None
            d, _ = json.JSONDecoder().raw_decode(h[i + len(k):])
            return d.get("loaderData", {}).get("track_page", {}).get("audioWithLyricsOption")
        except Exception:
            time.sleep(0.5)
    return None


def expand(tid):
    a = fetch(tid)
    if not a:
        with lock:
            fail.append(tid)
        return []
    with lock:
        if a.get("trackName"):
            catalog[tid] = a.get("trackName")
    out = []
    for item in a.get("artistTracks", []) or []:
        tr = item.get("track", {})
        t = tr.get("id")
        if not t:
            continue
        arts = [x.get("name") for x in (tr.get("artists") or [])]
        if ARTIST in arts:
            out.append((str(t), tr.get("name")))
        with lock:
            catalog.setdefault(str(t), tr.get("name"))
    return out


def main():
    seeds = sys.argv[1:] or ["7696204019388024841"]
    todo = set(seeds)
    done = set()
    max_rounds = int(sys.argv[0] and 25)
    for r in range(1, max_rounds + 1):
        batch = [t for t in todo if t not in done]
        if not batch:
            break
        done |= set(batch)
        with ThreadPoolExecutor(max_workers=10) as ex:
            for res in ex.map(expand, batch):
                for tid, name in res:
                    if tid not in catalog or not catalog.get(tid):
                        catalog[tid] = name
        new = set(catalog) - done
        print(f"round {r}: 处理 {len(batch)} 首 | 目录累计 {len(catalog)} | 待处理 {len(new)}", flush=True)
        todo = set(catalog)
        if len(new) == 0:
            break
        if len(catalog) > 4000:
            print("达到上限 4000，停止扩张")
            break
    json.dump(catalog, open("catalog.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n目录共", len(catalog), "首 -> catalog.json")


if __name__ == "__main__":
    main()
