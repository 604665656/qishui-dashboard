"""构建「歌名+播放+点赞+收藏+评论」总表，按 track_id 对齐已下载曲库。
数据源：
 - 曲库索引.json  : 已下载曲库（track_id -> title/file/ok/bytes）
 - stats_list.json: 创作者后台列表（汽水累计播放量/抖音投稿量/7日热度/环比）
 - overview_stats.json: 每首 8 个 7日指标（含 汽水播放量/抖音视频播放量/抖音视频点赞数）
输出：数据总表.csv（UTF-8-BOM，Excel 友好）
"""
import json, os, csv

def load(p, default):
    if not os.path.exists(p): return default
    return json.load(open(p, encoding="utf-8"))

# 1) 已下载曲库（基础表）
lib = load("曲库索引.json", [])
lib_by_id = {}
for it in lib:
    tid = str(it.get("track_id", ""))
    lib_by_id[tid] = it

# 2) 列表统计
lst = load("stats_list.json", {"songs": []})
list_by_id = {}
for s in lst.get("songs", []):
    list_by_id[str(s.get("metaSongId", ""))] = s

# 3) overview
ov = load("overview_stats.json", {"metrics": {}})
ov_by_id = {str(k): v for k, v in ov.get("metrics", {}).items()}

# metricType -> 中文标签（来自详情页 DOM 实测）
MT_LABEL = {
    1: "汽水7日热度指数", 2: "汽水7日播放量", 3: "汽水付费播放指数",
    4: "汽水搜播指数", 5: "抖音7日投稿量", 6: "抖音7日热度指数",
    7: "抖音视频播放量", 8: "抖音视频点赞数",
}

# 合并：以已下载曲库为基准，再并入后台列表的全部歌曲
all_ids = list(lib_by_id.keys())
for tid in list_by_id:
    if tid not in all_ids: all_ids.append(tid)

rows = []
for tid in all_ids:
    it = lib_by_id.get(tid, {})
    ls = list_by_id.get(tid, {})
    ovv = ov_by_id.get(tid, {})
    name = it.get("title") or ls.get("title") or ""
    rows.append({
        "track_id": tid,
        "歌名": name,
        "作者": it.get("artist") or ls.get("artistName") or "许许许许许丶若辰",
        "汽水累计播放量": ls.get("lunaPlayAll", ""),
        "抖音累计投稿量": ls.get("douyinPublishAll", ""),
        "汽水播放量昨日环比": ls.get("lunaPlay1dRate", ""),
        "汽水播放量7日环比": ls.get("lunaPlay7dRate", ""),
        "抖音投稿量昨日环比": ls.get("douyinPublish1dRate", ""),
        "抖音投稿量7日环比": ls.get("douyinPublish7dRate", ""),
        "汽水7日热度指数": ls.get("lunaPopularity7d", ""),
        "抖音7日热度指数": ls.get("douyinPopularity7d", ""),
        "汽水7日播放量": ovv.get("2", ""),
        "汽水付费播放指数": ovv.get("3", ""),
        "汽水搜播指数": ovv.get("4", ""),
        "抖音7日投稿量": ovv.get("5", ""),
        "抖音视频播放量": ovv.get("7", ""),
        "抖音视频点赞数": ovv.get("8", ""),  # 唯一可用的“点赞”指标
        "已下载音频": "是" if it.get("ok") else ("否" if tid in lib_by_id else ""),
        "音频文件": it.get("file", "") + ".m4a" if it.get("file") else "",
    })

# 按汽水累计播放量降序（空值排最后）
def num(v):
    try: return int(str(v).replace(",", ""))
    except Exception: return -1
rows.sort(key=lambda r: num(r["汽水累计播放量"]), reverse=True)

cols = ["track_id", "歌名", "作者", "汽水累计播放量", "抖音累计投稿量",
        "汽水播放量昨日环比", "汽水播放量7日环比", "抖音投稿量昨日环比", "抖音投稿量7日环比",
        "汽水7日热度指数", "抖音7日热度指数", "汽水7日播放量", "汽水付费播放指数",
        "汽水搜播指数", "抖音7日投稿量", "抖音视频播放量", "抖音视频点赞数",
        "已下载音频", "音频文件"]

out = "数据总表.csv"
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows: w.writerow(r)

print(f"写出 {out}：共 {len(rows)} 行")
print(f"  有列表统计: {sum(1 for r in rows if r['汽水累计播放量']!='')}")
print(f"  有 overview: {sum(1 for r in rows if r['抖音视频点赞数']!='')}")
print(f"  已下载音频: {sum(1 for r in rows if r['已下载音频']=='是')}")
