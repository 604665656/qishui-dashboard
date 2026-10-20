"""从汽水音乐分享页 SSR 数据提取曲目音频直链与歌词（无需 Cookie）。"""
import json, os, re, sys, time
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SHARE = "https://music.douyin.com/qishui/share/track?track_id={tid}"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


def get(url, referer="https://music.douyin.com/"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def router_data(tid):
    html = get(SHARE.format(tid=tid)).decode("utf-8", "ignore")
    key = "_ROUTER_DATA = "
    i = html.find(key)
    if i < 0:
        return None
    d, _ = json.JSONDecoder().raw_decode(html[i + len(key):])
    return d.get("loaderData", {}).get("track_page", {}).get("audioWithLyricsOption")


def fmt(ms):
    ms = int(round(float(ms)))
    m, s = divmod(ms, 60000)
    return f"{m:02d}:{s // 1000:02d}.{(s % 1000) // 10:02d}"


def to_lrc(lyrics):
    if not lyrics:
        return ""
    out = []
    for sen in lyrics.get("sentences", []):
        txt = (sen.get("text") or "").strip()
        if not txt:
            continue
        out.append(f"[{fmt(sen.get('startMs', 0))}]{txt}")
    return "\n".join(out) + "\n"


def safe(name):
    return re.sub(r'[\\/:*?"<>|]', "_", (name or "unknown").strip())


def save_bytes(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://music.douyin.com/"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def main():
    track_ids = sys.argv[1:]
    index = []
    for n, tid in enumerate(track_ids, 1):
        print(f"[{n}/{len(track_ids)}] track_id={tid} ...", flush=True)
        try:
            a = router_data(tid)
        except Exception as e:
            print("   SSR 获取失败:", e)
            continue
        if not a:
            print("   无 SSR 数据，跳过")
            continue
        title = a.get("trackName") or f"track_{tid}"
        artist = a.get("artistName") or ""
        url = a.get("url")
        base = safe(f"{title} - {artist}") if artist else safe(title)
        d = os.path.join(OUT, base)
        os.makedirs(d, exist_ok=True)

        size = 0
        if url:
            try:
                size = save_bytes(url, os.path.join(d, base + ".m4a"))
            except Exception as e:
                print("   音频下载失败:", e)
        else:
            print("   无音频直链")

        lrc = to_lrc(a.get("lyrics"))
        if lrc:
            open(os.path.join(d, base + ".lrc"), "w", encoding="utf-8").write(lrc)
            plain = "\n".join(l.split("]", 1)[1] for l in lrc.strip().split("\n")) + "\n"
            open(os.path.join(d, base + ".txt"), "w", encoding="utf-8").write(plain)
        else:
            print("   无歌词")

        meta = {
            "track_id": tid, "title": title, "artist": artist,
            "artist_id": a.get("artistIdStr"), "album": a.get("trackInfo", {}).get("album"),
            "duration_sec": a.get("duration"), "audio_bytes": size,
            "audio_url_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        index.append(meta)
        print(f"   OK {title} / {artist} / {size // 1024} KB / 歌词 {len(lrc)} 字符")
        time.sleep(0.6)

    json.dump(index, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n完成，共", len(index), "首 →", OUT)


if __name__ == "__main__":
    main()
