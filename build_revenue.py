import csv,json,os,datetime
base="C:/Users/60466/WorkBuddy/2026-10-17-14-52-57/"
months=[('202604',24.96),('202605',407.60),('202606',878.01),('202607',610.52),('202608',273.63)]
STATUS={11:"结算成功"}

# 1) 月度汇总（来自 query_audit_order）
orders=[
 ("202608","TT7687016259842214690",273.63,"2026-09-21"),
 ("202607","TT7676541649912859443",610.52,"2026-08-24"),
 ("202606","TT7663536146223450895",878.01,"2026-07-21"),
 ("202605","TT7654665545375107886",407.60,"2026-06-26"),
 ("202604","TT7641484524387928875",24.96,"2026-05-21"),
]
with open(base+"收益月度汇总.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f)
    w.writerow(["结算周期(年月)","结算单号","结算金额(元)","结算状态","结算日期"])
    tot=0
    for cy,ono,amt,dt in orders:
        w.writerow([cy,ono,f"{amt:.2f}","结算成功",dt]); tot+=amt
    w.writerow(["合计","","{:.2f}".format(tot),"",""])

# 2) 逐歌明细 长表
lib=json.load(open(base+"曲库索引.json",encoding="utf-8"))
lib_ids={it['track_id'] for it in lib}
cols=["月份","结算单日期","收入日期","歌曲id","歌曲名称","歌手名称","平台","收入类型","权利比例",
      "免费播放量","付费播放量","下载量","订购量","广告收入","付费收入","分成收入","对齐曲库"]
long_rows=[]
agg={}  # track_id -> {name, artist, per_month: {month: amount}, total}
for cy,_ in months:
    fn=base+f"结算明细/结算明细_{cy}.csv"
    with open(fn,encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sid=r["歌曲id"]; name=r["歌曲名称"]; artist=r["歌手名称"]
            try: amt=float(r["分成收入"])
            except: amt=0.0
            row=[cy,r["结算单日期"],r["收入日期"],sid,name,artist,r["平台"],r["收入类型"],r["权利比例"],
                 r["免费播放量"],r["付费播放量"],r["下载量"],r["订购量"],r["广告收入"],r["付费收入"],r["分成收入"],
                 "是" if sid in lib_ids else "否"]
            long_rows.append(row)
            if sid not in agg: agg[sid]={"name":name,"artist":artist,"pm":{},"total":0.0}
            agg[sid]["pm"][cy]=agg[sid]["pm"].get(cy,0.0)+amt
            agg[sid]["total"]+=amt
with open(base+"收益逐歌明细_全量.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f); w.writerow(cols)
    for row in long_rows: w.writerow(row)

# 3) 逐歌累计
with open(base+"收益逐歌累计.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f)
    w.writerow(["歌曲id","歌曲名称","演唱者","累计分成收入(元)","有收益月份数","各月(元: 202604,202605,202606,202607,202608)"])
    # sort by total desc
    for sid,a in sorted(agg.items(),key=lambda kv:kv[1]["total"],reverse=True):
        pm=a["pm"]
        detail=",".join(f"{m}:{pm.get(m,0):.2f}" for m,_ in months)
        w.writerow([sid,a["name"],a["artist"],f"{a['total']:.2f}",len(pm),detail])

print("月度汇总: 5 行, 合计 {:.2f} 元".format(tot))
print("逐歌明细长表: {} 行".format(len(long_rows)))
print("逐歌累计: {} 首有收益; 全平台累计分成 {:.2f} 元".format(len(agg),sum(a['total'] for a in agg.values())))
