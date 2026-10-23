# -*- coding: utf-8 -*-
"""
汽水音乐数据 · 本地离线看板生成器
================================
把已抓取的 CSV（当日数据 / 月度收益 / 逐歌明细 / 歌曲累计）内嵌为一个
自包含 HTML 看板，纯本地、零外部依赖、双击即开，不消耗任何模型 TOKEN。

用法：python build_dashboard.py
产物：汽水数据看板.html （同目录）
"""
import csv, json, os, sys, datetime
import acctpath  # 账号隔离：读当前账号数据目录
try:
    import contact_assets  # 联系合作 / 赞助二维码（base64 内嵌）
except Exception:
    contact_assets = None

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)          # EXE 单文件：数据在同目录
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# 当前账号数据目录（accounts/{uid}；首次未迁走时回退根目录/ _legacy）
DATA_DIR = acctpath.active_account_dir()
if DATA_DIR != BASE:
    print("数据目录:", DATA_DIR)

def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

# ---------- 1. 当日/最近一日数据（稳定文件名，始终为最新一日） ----------
yest = read_csv(os.path.join(DATA_DIR, '汽水昨日数据.csv'))

# 「付费播放」数据源：概览接口 metricType=3（汽水付费播放指数，与播放量同量纲）。
# 旧版 CSV 无此列，优先读 CSV 列，缺失则回退 overview_1d.json。
_pay_map = {}
try:
    _ov1 = json.load(open(os.path.join(DATA_DIR, 'overview_1d.json'), encoding='utf-8'))
    for _sid, _m in (_ov1.get('metrics') or {}).items():
        _v = _m.get('3')
        if _v is not None:
            _pay_map[str(_sid)] = num(_v)
except Exception:
    pass

yest_rows = []
# 列名兼容：新版 CSV 用「当日X」，旧版用「昨日汽水X」
_yk = lambda r, new, old: (r.get(new) if r.get(new) not in (None, '') else r.get(old, ''))
yest_date = (_yk(yest[0], '数据日期', '数据日期') if yest else '')
yest_latest_date = (yest[0].get('最近一日日期') or '') if yest else ''
yest_total_play = 0
yest_total_hot = 0
yest_total_latest = 0.0
for r in yest:
    play = num(_yk(r, '当日播放量', '昨日汽水播放量'))
    hot = num(_yk(r, '当日热度指数', '昨日汽水热度指数'))
    latest = num(r.get('最近一日播放', ''))
    _pr = _yk(r, '当日付费播放指数', '昨日付费播放指数')
    pay = num(_pr) if _pr not in ('', None) else _pay_map.get(str(r['track_id']), 0.0)
    # 极小量级时平台两指标口径不同，指数可能略高于总播放 —— 封顶保证 免费+付费=总播放
    if pay < 0:
        pay = 0.0
    if play >= 0 and pay > play:
        pay = play
    free = max(0.0, play - pay)
    yest_total_play += play
    yest_total_hot += hot
    yest_total_latest += latest
    yest_rows.append({
        'tid': r['track_id'],
        'name': r['歌名'],
        'artist': r['作者'],
        'play': play,
        'pay': pay,
        'free': free,
        'hot': hot,
        'latest': latest,
    })
yest_rows.sort(key=lambda x: x['play'], reverse=True)
yest_total_pay = sum(x['pay'] for x in yest_rows)
yest_total_free = sum(x['free'] for x in yest_rows)

# ---------- 2. 月度收益汇总 ----------
msum = read_csv(os.path.join(DATA_DIR, '收益月度汇总.csv'))
monthly_summary = []
for r in msum:
    m = r['结算周期(年月)']
    if not (m and m.isdigit() and len(m) == 6):   # 跳过「合计」等非月份行
        continue
    monthly_summary.append({
        'month': m,
        'settle_date': r.get('结算日期', ''),
        'amount': num(r['结算金额(元)']),
        'status': r.get('结算状态', ''),
        'order_no': r.get('结算单号', ''),
    })
monthly_summary.sort(key=lambda x: x['month'])

# ---------- 3. 逐歌明细（全量） + 按平台/月份聚合 ----------
detail = read_csv(os.path.join(DATA_DIR, '收益逐歌明细_全量.csv'))
detail_rows = []
months_set = set()
platforms_set = set()
for r in detail:
    m = r['月份']
    months_set.add(m)
    platforms_set.add(r['平台'])
    detail_rows.append({
        'month': m,
        'income_date': r.get('收入日期', ''),
        'settle': r.get('结算单日期', ''),
        'tid': r['歌曲id'],
        'name': r['歌曲名称'],
        'artist': r.get('歌手名称', ''),
        'platform': r['平台'],
        'income_type': r.get('收入类型', ''),
        'right': r.get('权利比例', ''),
        'free': r.get('免费播放量', ''),
        'pay': r.get('付费播放量', ''),
        'dl': r.get('下载量', ''),
        'order': r.get('订购量', ''),
        'share': num(r['分成收入']),
        'aligned': r.get('对齐曲库', ''),
    })

# 每首歌「首发收益月」（平台接口无发布日期，用首次有收益的月份作代理）
publish_min = {}
for r in detail_rows:
    if r['share'] > 0:
        tid = r['tid']
        if tid not in publish_min or r['month'] < publish_min[tid]:
            publish_min[tid] = r['month']

# 月度·平台聚合（汽水音乐播放 vs 分成）
agg = {}  # month -> platform -> {free,pay,play,sr}
for r in detail_rows:
    m = r['month']; p = r['platform']
    ff = num(r['free']) if r['free'] not in ('', 'N/A') else 0.0
    pp = num(r['pay']) if r['pay'] not in ('', 'N/A') else 0.0
    sr = r['share']
    a = agg.setdefault(m, {}).setdefault(p, {'free': 0.0, 'pay': 0.0, 'sr': 0.0})
    a['free'] += ff; a['pay'] += pp; a['sr'] += sr

monthly_play = []  # 汽水音乐
for m in sorted(months_set):
    a = agg.get(m, {}).get('汽水音乐', {'free': 0, 'pay': 0, 'sr': 0})
    play = a['free'] + a['pay']
    rpm = a['sr'] / play * 1000 if play else 0
    payshare = a['pay'] / play * 100 if play else 0
    monthly_play.append({
        'month': m,
        'free': a['free'],
        'pay': a['pay'],
        'play': play,
        'sr': a['sr'],
        'rpm': rpm,
        'payshare': payshare,
    })

# ---------- 4. 收入公式拆解（汽水音乐，按权利比例归一化全局回归） ----------
def share_of(rp):
    if '词50%' in rp and '100%' not in rp:
        return 0.5
    if '100%' in rp:
        return 1.0
    return 0.5

Sx1 = Sx2 = Sx1x1 = Sx1x2 = Sx2x2 = Sx1y = Sx2y = 0.0
n = 0
for r in detail_rows:
    if r['platform'] != '汽水音乐':
        continue
    f = num(r['free']) if r['free'] not in ('', 'N/A') else 0.0
    pp = num(r['pay']) if r['pay'] not in ('', 'N/A') else 0.0
    s = r['share']
    if (f + pp) > 0 and s > 0:
        sh = share_of(r['right'])
        base = s / sh
        Sx1 += f; Sx2 += pp; Sx1x1 += f * f; Sx1x2 += f * pp
        Sx2x2 += pp * pp; Sx1y += f * base; Sx2y += pp * base
        n += 1
det = Sx1x1 * Sx2x2 - Sx1x2 * Sx1x2
rf = (Sx1y * Sx2x2 - Sx2y * Sx1x2) / det if abs(det) > 1e-12 else 0
rp_ = (Sx1x1 * Sx2y - Sx1x2 * Sx1y) / det if abs(det) > 1e-12 else 0

formula = {
    'n': n,
    'rf_per_play': rf,
    'rp_per_play': rp_,
    'rf_per_k': rf * 1000,
    'rp_per_k': rp_ * 1000,
    'pay_mult': (rp_ / rf) if rf else 0,
}

# 逐月基础单价（分两组）以验证下滑趋势
monthly_rpm = []
for m in sorted(months_set):
    rows_m = [r for r in detail_rows if r['month'] == m and r['platform'] == '汽水音乐']
    pl = sum((num(r['free']) if r['free'] not in ('', 'N/A') else 0) +
             (num(r['pay']) if r['pay'] not in ('', 'N/A') else 0) for r in rows_m)
    sr = sum(r['share'] for r in rows_m)
    monthly_rpm.append({'month': m, 'rpm': sr / pl * 1000 if pl else 0, 'sr': sr, 'play': pl})

# ---------- 5. 歌曲累计榜 ----------
acc = read_csv(os.path.join(DATA_DIR, '收益逐歌累计.csv'))
acc_rows = []
for r in acc:
    acc_rows.append({
        'tid': r.get('歌曲id', ''),
        'name': r.get('歌曲名称', ''),
        'artist': r.get('演唱者', ''),
        'total': num(r.get('累计分成收入(元)', '')),
        'months': num(r.get('有收益月份数', '')),
        'publish': publish_min.get(r.get('歌曲id', ''), ''),
    })
acc_rows.sort(key=lambda x: x['total'], reverse=True)

# ---------- 汇总数字 ----------
total_revenue = sum(m['amount'] for m in monthly_summary)
songs_with_rev = len(acc_rows)

# ---------- 6. 版权风险 & 收益异常 排查（复用 review_songs 分析） ----------
try:
    import review_songs
    _rv_rows, _rv_lib = review_songs.analyze()
except Exception as e:
    _rv_rows, _rv_lib = [], {}
    print('排查分析跳过:', e)
from collections import Counter
_rv_risk = Counter(r['risk'] for r in _rv_rows)
_rv_tag = Counter()
for r in _rv_rows:
    for t in (r.get('tags') or '').split(';'):
        if t:
            _rv_tag[t] += 1

DATA = {
    'yest_date': yest_date,
    'yest_total_play': yest_total_play,
    'yest_total_hot': yest_total_hot,
    'yest_total_pay': yest_total_pay,
    'yest_total_free': yest_total_free,
    'yest_total_latest': yest_total_latest,
    'yest_latest_date': yest_latest_date,
    'yest_rows': yest_rows,
    'monthly_summary': monthly_summary,
    'monthly_play': monthly_play,
    'monthly_rpm': monthly_rpm,
    'detail_rows': detail_rows,
    'months': sorted(months_set),
    'platforms': sorted(platforms_set),
    'formula': formula,
    'acc_rows': acc_rows,
    'total_revenue': total_revenue,
    'songs_with_rev': songs_with_rev,
    'gen_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'review_rows': _rv_rows,
    'review_risk': dict(_rv_risk),
    'review_tag': dict(_rv_tag),
    'support_assets': (contact_assets.ASSETS if contact_assets else {}),
    'support_info': (contact_assets.INFO if contact_assets else {}),
}

json_str = json.dumps(DATA, ensure_ascii=False)
json_str = json_str.replace('</', '<\\/')

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>汽水音乐数据看板（本地离线）</title>
<style>
:root{
  --bg:#f5f7fa; --card:#ffffff; --ink:#1f2733; --sub:#6b7785; --line:#e6ebf0;
  --brand:#2f6df0; --brand2:#13c2a2; --warn:#e8920c; --red:#e5484d; --green:#2faa5b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif;font-size:14px;line-height:1.5}
header{padding:20px 26px;background:linear-gradient(120deg,#2f6df0,#13c2a2);color:#fff}
header h1{margin:0;font-size:20px;font-weight:700}
header .meta{margin-top:6px;font-size:12.5px;opacity:.92}
.badge{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);
  padding:2px 9px;border-radius:20px;font-size:12px;margin-right:8px}
.tabs{display:flex;flex-wrap:wrap;gap:4px;padding:12px 20px 0;background:#fff;border-bottom:1px solid var(--line)}
.tab{padding:9px 16px;cursor:pointer;border:1px solid transparent;border-bottom:none;border-radius:8px 8px 0 0;color:var(--sub);font-weight:600}
.tab.active{color:var(--brand);background:var(--bg);border-color:var(--line)}
.wrap{padding:20px 26px 60px;max-width:1280px;margin:0 auto}
.panel{display:none}
.panel.active{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:18px;
  box-shadow:0 1px 3px rgba(20,40,80,.04)}
.grid{display:grid;gap:14px}
.g4{grid-template-columns:repeat(4,1fr)}
.g5{grid-template-columns:repeat(5,1fr)}
@media(max-width:1100px){.g5{grid-template-columns:repeat(2,1fr)}}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.kpi .v{font-size:24px;font-weight:700;color:var(--brand)}
.kpi .l{font-size:12.5px;color:var(--sub);margin-top:4px}
.kpi .s{font-size:12px;color:var(--sub);margin-top:2px}
h2{font-size:16px;margin:0 0 12px;display:flex;align-items:center;gap:8px}
h2 .tag{font-size:11px;font-weight:600;color:#fff;background:var(--brand);padding:2px 8px;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--sub);font-weight:600;position:sticky;top:0;background:#fff;cursor:pointer;user-select:none}
tbody tr:hover{background:#f7faff}
.tblbox{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.bar{height:9px;border-radius:5px;background:var(--brand);display:inline-block;vertical-align:middle}
.controls{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px;align-items:center}
.controls input,.controls select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff;color:var(--ink)}
.controls input[type=text]{min-width:220px}
.note{font-size:12.5px;color:var(--sub);background:#f0f6ff;border:1px solid #d6e6ff;border-radius:8px;padding:10px 12px;margin-top:10px}
.formula{font-family:"SFMono-Regular",Consolas,monospace;background:#0f1729;color:#cfe3ff;padding:14px 16px;border-radius:10px;font-size:13px;line-height:1.7;overflow:auto}
.formula b{color:#7fe0c0}
.svgchart{width:100%}
.legend{display:flex;gap:16px;font-size:12.5px;color:var(--sub);margin-top:8px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:middle}
.pill{font-size:11px;padding:1px 7px;border-radius:10px;background:#eef3ff;color:var(--brand)}
.muted{color:var(--sub)}
footer{text-align:center;color:var(--sub);font-size:12px;padding:24px}
.empty{color:var(--sub);padding:20px;text-align:center}
.contact-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;gap:16px;align-items:center}
.contact-card .cc-body{flex:1;min-width:0}
.cc-title{font-weight:700;font-size:15px;margin-bottom:8px;color:var(--ink)}
.cc-line{font-size:13px;color:var(--sub);margin:4px 0;line-height:1.5}
.contact-card img{width:140px;max-width:38%;height:auto;border-radius:10px;border:1px solid var(--line);background:#fff}
.qr-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.qr-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.qr-card img{width:100%;max-width:230px;height:auto;border-radius:10px}
.qr-card .cap{font-size:12.5px;color:var(--sub);margin-top:10px}
@media(max-width:760px){.qr-grid{grid-template-columns:1fr}.contact-card{flex-direction:column;align-items:flex-start}.contact-card img{width:180px;max-width:100%}}
</style>
</head>
<body>
<header>
  <h1>汽水音乐 · 创作者数据看板</h1>
  <div class="meta">
    <span class="badge">本地离线</span>
    <span class="badge">无需联网 / 模型 TOKEN</span>
    <span class="badge" id="genTime"></span>
    数据快照：当日 <b id="yestDate"></b> ｜ 结算月份 __MONTHS__
  </div>
</header>
<div class="tabs" id="tabs">
  <div class="tab active" data-p="overview">概览</div>
  <div class="tab" data-p="yest">当日播放 &amp; 热度</div>
  <div class="tab" data-p="monthly">月度收益汇总</div>
  <div class="tab" data-p="compare">播放 vs 收益</div>
  <div class="tab" data-p="detail">逐歌收益明细</div>
  <div class="tab" data-p="acc">歌曲累计榜</div>
  <div class="tab" data-p="formula">收入公式</div>
  <div class="tab" data-p="review">排查 / 版权风险</div>
  <div class="tab" data-p="support">联系 &amp; 赞助</div>
</div>
<div class="wrap">
  <section class="panel active" id="p-overview"></section>
  <section class="panel" id="p-yest"></section>
  <section class="panel" id="p-monthly"></section>
  <section class="panel" id="p-compare"></section>
  <section class="panel" id="p-detail"></section>
  <section class="panel" id="p-acc"></section>
  <section class="panel" id="p-formula"></section>
  <section class="panel" id="p-review"></section>
  <section class="panel" id="p-support"></section>
</div>
<footer>本地数据看板 · 由已抓取 CSV 生成 · 双击本文件即可离线查看</footer>

<script id="payload" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);
const fmt = (n,d=0)=> (n==null?'':Number(n).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d}));
const yuan = (n)=> '¥'+fmt(n,2);
const fmtK = (n)=> n>=10000? (n/10000).toFixed(1)+'万' : fmt(n);
document.getElementById('genTime').textContent='生成 '+DATA.gen_time;
document.getElementById('yestDate').textContent=DATA.yest_date;

// 选项卡
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('p-'+t.dataset.p).classList.add('active');
    render(t.dataset.p);
  };
});

// ---- SVG 柱状图 ----
function barChart(el, items, opts={}){
  const W=opts.w||820, H=opts.h||260, pad=42;
  const max=Math.max(...items.map(i=>i.v||0),1);
  const n=items.length, bw=Math.min(54,(W-pad*2)/n*0.6);
  const gap=(W-pad*2)/n;
  let s=`<svg class="svgchart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  // y grid
  for(let g=0;g<=4;g++){
    const y=H-pad-(H-pad*2)*g/4; const val=max*g/4;
    s+=`<line x1="${pad}" y1="${y}" x2="${W-pad}" y2="${y}" stroke="#eef2f7"/>`;
    s+=`<text x="${pad-6}" y="${y+4}" text-anchor="end" font-size="10" fill="#9aa7b5">${opts.fmtY?opts.fmtY(val):fmt(val)}</text>`;
  }
  items.forEach((it,i)=>{
    const x=pad+gap*i+(gap-bw)/2;
    const h=(H-pad*2)*(it.v||0)/max; const y=H-pad-h;
    const c=it.c||'#2f6df0';
    s+=`<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="4" fill="${c}"><title>${it.label}: ${it.tip||it.v}</title></rect>`;
    s+=`<text x="${x+bw/2}" y="${H-pad+16}" text-anchor="middle" font-size="11" fill="#5b6775">${it.label}</text>`;
    s+=`<text x="${x+bw/2}" y="${y-5}" text-anchor="middle" font-size="10.5" fill="#33414f">${opts.fmtTop?opts.fmtTop(it.v):fmt(it.v)}</text>`;
  });
  s+=`<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#cfd8e3"/>`;
  s+=`</svg>`;
  el.innerHTML=s;
}

// ---- 组合图：柱(播放) + 线(分成) ----
function comboChart(el, items){
  const W=860,H=280,pad=48;
  const maxP=Math.max(...items.map(i=>i.play),1);
  const maxS=Math.max(...items.map(i=>i.sr),1);
  const n=items.length, gap=(W-pad*2)/n, bw=Math.min(46,gap*0.5);
  let s=`<svg class="svgchart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  for(let g=0;g<=4;g++){
    const y=H-pad-(H-pad*2)*g/4;
    s+=`<line x1="${pad}" y1="${y}" x2="${W-pad}" y2="${y}" stroke="#eef2f7"/>`;
    s+=`<text x="${pad-6}" y="${y+4}" text-anchor="end" font-size="10" fill="#9aa7b5">${fmtK(maxP*g/4)}</text>`;
    s+=`<text x="${W-pad+6}" y="${y+4}" text-anchor="start" font-size="10" fill="#13c2a2">${fmt(maxS*g/4,0)}</text>`;
  }
  // bars (play)
  items.forEach((it,i)=>{
    const x=pad+gap*i+(gap-bw)/2; const h=(H-pad*2)*it.play/maxP; const y=H-pad-h;
    s+=`<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="4" fill="#2f6df0" opacity=".85"><title>${it.month} 汽水播放 ${fmt(it.play)}</title></rect>`;
    s+=`<text x="${x+bw/2}" y="${H-pad+16}" text-anchor="middle" font-size="11" fill="#5b6775">${it.month}</text>`;
  });
  // line (sr)
  const pts=items.map((it,i)=>{const x=pad+gap*i+gap/2; const y=H-pad-(H-pad*2)*it.sr/maxS; return [x,y,it];});
  s+=`<polyline fill="none" stroke="#13c2a2" stroke-width="2.5" points="${pts.map(p=>p[0]+','+p[1]).join(' ')}"/>`;
  pts.forEach(p=>{
    s+=`<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#13c2a2"><title>${p[2].month} 汽水分成 ${yuan(p[2].sr)}</title></circle>`;
    s+=`<text x="${p[0]}" y="${p[1]-9}" text-anchor="middle" font-size="10" fill="#0e9c82">${fmt(p[2].sr,0)}</text>`;
  });
  s+=`<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#cfd8e3"/>`;
  s+=`</svg>`;
  el.innerHTML=s;
}

function sortableTable(headers, rows, opt={}){
  const tbl=document.createElement('table');
  const thead=document.createElement('thead'); const tr=document.createElement('tr');
  headers.forEach((h,i)=>{const th=document.createElement('th');th.textContent=h;th.onclick=()=>{
    rows.sort((a,b)=>{let x=a[i],y=b[i];if(typeof x==='number')return (y-x)*(th._a?-1:1);return String(x).localeCompare(String(y),'zh')*(th._a?-1:1);});
    th._a=!th._a; renderRows();
  };tr.appendChild(th);});
  thead.appendChild(tr); tbl.appendChild(thead);
  const tb=document.createElement('tbody'); tbl.appendChild(tb);
  function renderRows(){
    tb.innerHTML='';
    const start=opt.page? opt.page*300:0; const slice=rows.slice(start,start+300);
    slice.forEach(r=>{const tr=document.createElement('tr');
      r.forEach((c,i)=>{const td=document.createElement('td');
        td.innerHTML = (opt.fmt&&opt.fmt[i])? opt.fmt[i](c): (c===''?'<span class="muted">—</span>':c);
        tr.appendChild(td);});
      tb.appendChild(tr);});
  }
  renderRows();
  return tbl;
}

const renderers={
  overview(){
    const el=document.getElementById('p-overview');
    const mp=DATA.monthly_play;
    const last=mp[mp.length-1]||{play:0,sr:0,rpm:0};
    const first=mp[0]||{play:0,sr:0,rpm:0};
    el.innerHTML=`
    <div class="grid g4">
      <div class="kpi"><div class="v">${fmtK(DATA.yest_total_play)}</div><div class="l">当日汽水总播放</div><div class="s">${DATA.yest_date}</div></div>
      <div class="kpi"><div class="v">${fmtK(DATA.yest_total_hot)}</div><div class="l">当日汽水总热度</div><div class="s">${DATA.yest_date}</div></div>
      <div class="kpi"><div class="v">${yuan(DATA.total_revenue)}</div><div class="l">累计已结算收益</div><div class="s">${DATA.monthly_summary.length} 个月</div></div>
      <div class="kpi"><div class="v">${fmt(DATA.songs_with_rev)}</div><div class="l">有收益歌曲数</div><div class="s">累计榜</div></div>
    </div>
    <div class="card">
      <h2><span class="tag">趋势</span>汽水音乐 月度播放 vs 分成收益</h2>
      <div id="ovChart"></div>
      <div class="legend"><span><i style="background:#2f6df0"></i>汽水总播放(柱)</span><span><i style="background:#13c2a2"></i>汽水分成收益(线,元)</span></div>
      <div class="note">月度 RPM（每千次播放收益）从首月 <b>${fmt(first.rpm,2)}</b> 元 降至近月 <b>${fmt(last.rpm,2)}</b> 元，呈明显下滑；收益增长主要靠播放量规模支撑。详见「播放 vs 收益」「收入公式」。</div>
    </div>`;
    comboChart(document.getElementById('ovChart'), DATA.monthly_play.map(m=>({month:m.month,play:m.play,sr:m.sr})));
  },
  yest(){
    const el=document.getElementById('p-yest');
    const payTot=DATA.yest_total_pay||0, freeTot=DATA.yest_total_free||0;
    const payRatio=DATA.yest_total_play>0?(payTot/DATA.yest_total_play*100):0;
    const hasLatest=(DATA.yest_total_latest>0)&&DATA.yest_latest_date;
    el.innerHTML=`
    <div class="grid ${hasLatest?'g5':'g4'}">
      <div class="kpi"><div class="v">${fmtK(DATA.yest_total_play)}</div><div class="l">当日总播放</div><div class="s">${DATA.yest_date}</div></div>
      <div class="kpi"><div class="v" style="color:#e8920c">${fmtK(payTot)}</div><div class="l">其中 付费播放</div><div class="s">占 ${fmt(payRatio,1)}%</div></div>
      <div class="kpi"><div class="v" style="color:#13c2a2">${fmtK(freeTot)}</div><div class="l">其中 免费播放(推算)</div><div class="s">总播放 − 付费</div></div>
      <div class="kpi"><div class="v">${fmtK(DATA.yest_total_hot)}</div><div class="l">当日总热度</div><div class="s">${DATA.yest_date}</div></div>
      ${hasLatest?`<div class="kpi"><div class="v" style="color:#4a7cf7">${fmtK(DATA.yest_total_latest)}</div><div class="l">最近一日播放<span class="pill">新</span></div><div class="s">${DATA.yest_latest_date}｜歌曲清单口径，与概览口径不同，仅看趋势</div></div>`:''}
    </div>
    <div class="note" style="margin:14px 0">概览数据日期：<b>${DATA.yest_date}</b>（单曲概览 period=1，KPI 与「总播放/付费/免费/热度」均取此口径，彼此自洽）。共 ${fmt(DATA.yest_rows.length)} 首。下表按「总播放」降序，可搜索歌名/作者。<br>
    ${hasLatest?`后台改版后<b>歌曲清单新增「最近一日播放」字段</b>（约 ${DATA.yest_latest_date}），比概览 period=1 新一天，但<b>两套口径不同、绝对值不可直接相加或比较</b>（概览与 7 日/月度结算自洽），该列仅供看单首歌的最新趋势。<br>`:''}
    「付费播放」取平台 <b>汽水付费播放指数</b>(metricType=3，与播放量同量纲)；「免费播放」= 总播放 − 付费播放（<b>推算值</b>）。极小量级歌曲两指标口径不同，付费可能略高于总播放，已封顶为总播放以保证 付费+免费=总播放。逐日真实「免费/付费播放量」计数平台未提供，月度真实计数见「月度收益汇总」「逐步收益明细」。</div>
    <div class="controls">
      <input type="text" id="yq" placeholder="搜索 歌名 / 作者">
      <span class="muted" id="yc"></span>
    </div>
    <div class="tblbox" id="ytbl"></div>`;
    const box=document.getElementById('ytbl');
    function draw(q=''){
      const hasLatest=(DATA.yest_total_latest>0)&&DATA.yest_latest_date;
      const rows=DATA.yest_rows.filter(r=>!q||r.name.includes(q)||r.artist.includes(q))
        .map(r=>{
          const base=[r.name,r.artist,fmt(r.play),fmt(r.pay),fmt(r.free),fmt(r.hot)];
          return hasLatest?[...base,fmt(r.latest),r.tid]:[...base,r.tid];
        });
      document.getElementById('yc').textContent='显示 '+rows.length+' 首';
      const heads=hasLatest?['歌名','作者','总播放','付费播放','免费播放(推算)','热度指数','最近一日(清单口径)','track_id']
                           :['歌名','作者','总播放','付费播放','免费播放(推算)','热度指数','track_id'];
      const fmts=hasLatest?[null,null,(v)=>'<b>'+v+'</b>',(v)=>'<span style="color:#e8920c">'+v+'</span>',(v)=>'<span style="color:#13c2a2">'+v+'</span>',null,(v)=>'<span style="color:#4a7cf7">'+v+'</span>',(v)=>'<span class="pill">'+v+'</span>']
                          :[null,null,(v)=>'<b>'+v+'</b>',(v)=>'<span style="color:#e8920c">'+v+'</span>',(v)=>'<span style="color:#13c2a2">'+v+'</span>',null,(v)=>'<span class="pill">'+v+'</span>'];
      box.innerHTML='';
      box.appendChild(sortableTable(heads,rows,{fmt:fmts}));
    }
    draw();
    document.getElementById('yq').oninput=e=>draw(e.target.value.trim());
  },
  monthly(){
    const el=document.getElementById('p-monthly');
    const rows=DATA.monthly_summary.map(m=>{
      const mp=DATA.monthly_play.find(x=>x.month===m.month)||{play:0,sr:0,rpm:0};
      return [m.month,m.settle_date,yuan(m.amount),m.status,fmtK(mp.play),yuan(mp.sr),fmt(mp.rpm,2)];
    });
    el.innerHTML=`
    <div class="card">
      <h2><span class="tag">月度</span>结算收益汇总（后台「结算成功」）</h2>
      <div class="tblbox" id="mtbl"></div>
      <div class="note">金额单位：元。合计 <b>${yuan(DATA.total_revenue)}</b>。汽水播放/分成来自逐歌结算明细（平台=汽水音乐）聚合；RPM=每千次播放收益。</div>
    </div>
    <div class="card">
      <h2><span class="tag">图</span>每月结算金额</h2>
      <div id="mbar"></div>
    </div>`;
    const box=document.getElementById('mtbl');
    box.appendChild(sortableTable(['月份','结算单日期','结算金额(元)','状态','汽水总播放','汽水分成(元)','RPM'],rows,
      {fmt:[null,null,(v)=>'<b>'+v+'</b>',(v)=>'<span class="pill">'+v+'</span>',null,null,null]}));
    barChart(document.getElementById('mbar'), DATA.monthly_summary.map(m=>({label:m.month,v:m.amount,tip:yuan(m.amount)})),{fmtY:v=>fmt(v,0),fmtTop:v=>fmt(v,0)});
  },
  compare(){
    const el=document.getElementById('p-compare');
    const rows=DATA.monthly_play.map(m=>[m.month,fmtK(m.free),fmtK(m.pay),fmtK(m.play),fmt(m.payshare*100,1)+'%',yuan(m.sr),fmt(m.rpm,2)]);
    el.innerHTML=`
    <div class="card">
      <h2><span class="tag">对比</span>汽水音乐 月度播放 vs 收益</h2>
      <div id="cbar"></div>
      <div class="legend"><span><i style="background:#2f6df0"></i>汽水总播放(柱)</span><span><i style="background:#13c2a2"></i>汽水分成收益(线,元)</span></div>
    </div>
    <div class="card">
      <h2><span class="tag">明细</span>月度播放构成与单价</h2>
      <div class="tblbox" id="ctbl"></div>
      <div class="note">付费播放占比与 RPM 逐月波动：免费播放是主体，付费播放单价约为免费的 ${fmt(DATA.formula.pay_mult,1)} 倍。RPM 下滑说明单位播放变现效率在走低。</div>
    </div>`;
    comboChart(document.getElementById('cbar'), DATA.monthly_play.map(m=>({month:m.month,play:m.play,sr:m.sr})));
    document.getElementById('ctbl').appendChild(sortableTable(['月份','免费播放','付费播放','总播放','付费占比','汽水分成(元)','RPM(元/千次)'],rows));
  },
  detail(){
    const el=document.getElementById('p-detail');
    el.innerHTML=`
    <div class="controls">
      <select id="dfm"><option value="">全部月份</option>${DATA.months.map(m=>`<option>${m}</option>`).join('')}</select>
      <select id="dfp"><option value="">全部平台</option>${DATA.platforms.map(p=>`<option>${p}</option>`).join('')}</select>
      <input type="text" id="dfs" placeholder="搜索 歌名 / 歌曲id">
      <span class="muted" id="dfc"></span>
    </div>
    <div class="tblbox" id="dtbl"></div>`;
    const box=document.getElementById('dtbl');
    function draw(){
      const fm=document.getElementById('dfm').value, fp=document.getElementById('dfp').value, q=document.getElementById('dfs').value.trim();
      let rows=DATA.detail_rows.filter(r=>(!fm||r.month===fm)&&(!fp||r.platform===fp)&&(!q||r.name.includes(q)||r.tid.includes(q)));
      rows=rows.map(r=>[r.month,r.settle||'-',r.name,r.artist,r.platform,r.right,r.free,r.pay,fmt(r.share,2),r.tid]);
      document.getElementById('dfc').textContent='共 '+rows.length+' 行 ｜ 合计分成 '+yuan(rows.reduce((s,r)=>s+Number(r[8].replace(/,/g,''))||0,0));
      box.innerHTML='';
      box.appendChild(sortableTable(['月份','结算单日期','歌曲名称','歌手','平台','权利比例','免费播放','付费播放','分成收入(元)','歌曲id'],rows,
        {fmt:[null,null,null,null,null,null,null,(v)=>v||'—',(v)=>v||'—',(v)=>'<b>'+v+'</b>',(v)=>'<span class="pill">'+v+'</span>']}));
    }
    draw();
    document.getElementById('dfm').onchange=draw;
    document.getElementById('dfp').onchange=draw;
    document.getElementById('dfs').oninput=draw;
  },
  acc(){
    const el=document.getElementById('p-acc');
    el.innerHTML=`
    <div class="note" style="margin-bottom:14px">按歌曲聚合的累计分成收入（来自逐歌明细），共 ${fmt(DATA.acc_rows.length)} 首有收益。按累计金额降序。
    「首发收益月」为发布日期代理：平台接口不返回歌曲发布日期，此处用该歌<b>首次产生收益的月份</b>近似。</div>
    <div class="controls"><input type="text" id="aq" placeholder="搜索 歌名 / 歌曲id"><span class="muted" id="ac"></span></div>
    <div class="tblbox" id="atbl"></div>`;
    const box=document.getElementById('atbl');
    function draw(q=''){
      const rows=DATA.acc_rows.filter(r=>!q||r.name.includes(q)||r.tid.includes(q))
        .map(r=>[r.name,r.artist,r.publish||'-',fmt(r.total,2),fmt(r.months,0)+' 个月',r.tid]);
      document.getElementById('ac').textContent='显示 '+rows.length+' 首';
      box.innerHTML='';
      box.appendChild(sortableTable(['歌曲名称','歌手','首发收益月','累计分成(元)','有收益月份','歌曲id'],rows,
        {fmt:[null,null,null,(v)=>'<b>'+v+'</b>',null,(v)=>'<span class="pill">'+v+'</span>']}));
    }
    draw();
    document.getElementById('aq').oninput=e=>draw(e.target.value.trim());
  },
  formula(){
    const f=DATA.formula;
    const el=document.getElementById('p-formula');
    const rpmRows=DATA.monthly_rpm.map(r=>[r.month,fmt(r.play,0),yuan(r.sr),fmt(r.rpm,3)]);
    el.innerHTML=`
    <div class="card">
      <h2><span class="tag">公式</span>收入拆解模型（汽水音乐）</h2>
      <div class="formula">
分成收入 = 权利比例 share × ( 免费播放 × <b>${f.rf_per_play.toFixed(7)}</b> + 付费播放 × <b>${f.rp_per_play.toFixed(7)}</b> )
其中 share：词50% 组 = 0.5 ，100% 组 = 1.0
等效每千次：免费 ≈ <b>${f.rf_per_k.toFixed(4)}</b> 元 ，付费 ≈ <b>${f.rp_per_k.toFixed(4)}</b> 元
付费单价 / 免费单价 ≈ <b>${f.pay_mult.toFixed(1)}</b> 倍
回归样本 n = ${f.n}（仅取 播放>0 且 分成>0 的汽水音乐行）
      </div>
      <div class="note">说明：直接对「每首歌」做全局线性回归会出现系数乱跳/负值，原因是 <b>权利比例并非常数</b>（同一作者不同歌有 50% 与 100% 两档）。这里先把分成收入按 share 归一化到「100% 权属」基准再做回归，得到干净的基础单价。免费/付费播放量来自结算明细 CSV 的「免费播放量/付费播放量」列。</div>
    </div>
    <div class="card">
      <h2><span class="tag">趋势</span>逐月每千次播放收益（RPM）</h2>
      <div class="tblbox" id="ftbl"></div>
      <div class="note">RPM 持续走低是核心风险信号：单纯靠播放量增长难以抵消单价下滑。9 月及以后若播放规模不再高增长，收益可能环比回落。</div>
    </div>`;
    document.getElementById('ftbl').appendChild(sortableTable(['月份','汽水总播放','汽水分成(元)','RPM(元/千次)'],rpmRows,
      {fmt:[null,null,null,(v)=>'<b>'+v+'</b>']}));
  },
  review(){
    const el=document.getElementById('p-review');
    const months=DATA.months||[];
    const risk=DATA.review_risk||{}, tag=DATA.review_tag||{};
    el.innerHTML=`
    <div class="note" style="margin-bottom:14px">
      <b>版权风险 / 收益异常 一键排查。</b>平台创作者后台<b>不提供</b>单曲"是否侵权/授权"官方字段，以下为基于本地「权利比例 / 对齐曲库 / 收益」的辅助筛查（非官方确权 / 法律意见）。
      风险分布：高 <b>${risk['高']||0}</b> ｜ 中(权利不全) <b>${risk['中']||0}</b> ｜ 低(完全自有) <b>${risk['低']||0}</b>。
      异常标签：${Object.entries(tag).map(e=>e[0]+' '+e[1]).join(' ｜ ')}。
    </div>
    <div class="card">
      <h2><span class="tag">日期筛选</span>自定义结算月份区间 · 免费/付费播放 & 分成</h2>
      <div class="controls">
        <select id="rvFrom"><option value="">起始月份</option>${months.map(m=>`<option>${m}</option>`).join('')}</select>
        <span>至</span>
        <select id="rvTo"><option value="">结束月份</option>${months.map(m=>`<option>${m}</option>`).join('')}</select>
        <select id="rvPf"><option value="">全部平台</option>${DATA.platforms.map(p=>`<option>${p}</option>`).join('')}</select>
        <input type="text" id="rvQ" placeholder="搜索 歌名 / 歌曲id">
        <span class="muted" id="rvC"></span>
      </div>
      <div class="tblbox" id="rvTbl"></div>
      <div class="note">区间筛选逐歌明细：可核对某段时间内每首歌的<b>免费播放 / 付费播放 / 分成收入</b>，上方合计为区间内总和。</div>
    </div>
    <div class="card">
      <h2><span class="tag">排查</span>有播放但 0 收益 筛查</h2>
      <div class="controls">
        <input type="number" id="zrMin" value="1" min="0" style="width:120px" title="最小总播放量（免费+付费）">
        <span>最小播放量</span>
        <select id="zrFrom"><option value="">起始月份</option>${months.map(m=>`<option>${m}</option>`).join('')}</select>
        <span>至</span>
        <select id="zrTo"><option value="">结束月份</option>${months.map(m=>`<option>${m}</option>`).join('')}</select>
        <select id="zrPf"><option value="">全部平台</option>${DATA.platforms.map(p=>`<option>${p}</option>`).join('')}</select>
        <input type="text" id="zrQ" placeholder="搜索 歌名 / 歌曲id">
        <span class="muted" id="zrC"></span>
      </div>
      <div class="tblbox" id="zrTbl"></div>
      <div class="note">列出「区间内总播放量 ≥ 阈值 但 分成收入 = 0」的歌曲（按歌曲id聚合免费/付费播放）。常见原因：权利比例非 100%（如词50%）使分成被按比例折后为 0、播放落在计费范围外、或结算滞后。<br>⚠️ 仅统计已进入结算明细 CSV 的歌曲；未出现在结算明细里的歌这里看不到。</div>
    </div>
    <div class="card">
      <h2><span class="tag">排查</span>版权风险 &amp; 收益异常清单</h2>
      <div class="controls">
        <select id="rvF"><option value="all">全部</option><option value="risk">仅风险(中/高)</option><option value="prob">仅异常标签</option></select>
        <input type="text" id="rvQ2" placeholder="搜索 歌名 / 歌曲id">
        <span class="muted" id="rvC2"></span>
      </div>
      <div class="tblbox" id="rvList"></div>
      <div class="note">「版权风险」看<b>权利比例</b>：录音/词/曲 任一&lt;100% 即"权利不全"(中)，三者均 0 为"零权利"(高)。「收益异常」含：零播放有收益 / 高播放零收益 / 未入库却有收益。<br>
      ⚠️ 「未在曲库 / 未入库却有收益」标签仅在<b>账号隔离</b>生效（曲库索引与当前账号一致）时可靠；若仍为旧账号残留，该标签会偏高，可忽略。</div>
    </div>`;
    const box=document.getElementById('rvTbl');
    const pn=(x)=>{const v=parseFloat(String(x==null?'':x).replace(/,/g,''));return isFinite(v)?v:0;};
    function drawRange(){
      const f=document.getElementById('rvFrom').value, t=document.getElementById('rvTo').value, q=document.getElementById('rvQ').value.trim(), pf=document.getElementById('rvPf').value;
      let rows=DATA.detail_rows.filter(r=>{
        if(f && r.month<f) return false;
        if(t && r.month>t) return false;
        if(pf && r.platform!==pf) return false;
        if(q && !(r.name.includes(q)||r.tid.includes(q))) return false;
        return true;
      });
      let freeSum=0,paySum=0,shareSum=0;
      rows.forEach(r=>{freeSum+=pn(r.free);paySum+=pn(r.pay);shareSum+=Number(r.share)||0;});
      rows=rows.map(r=>[r.month,r.settle||'-',r.name,r.artist,r.platform,r.right,r.free,r.pay,fmt(r.share,2),r.tid]);
      document.getElementById('rvC').textContent='共 '+rows.length+' 行 ｜ 免费播放 '+fmtK(freeSum)+' ｜ 付费播放 '+fmtK(paySum)+' ｜ 总播放 '+fmtK(freeSum+paySum)+' ｜ 合计分成 '+yuan(shareSum);
      box.innerHTML='';
      box.appendChild(sortableTable(['月份','结算单日期','歌曲名称','歌手','平台','权利比例','免费播放','付费播放','分成收入(元)','歌曲id'],rows,
        {fmt:[null,null,null,null,null,null,null,(v)=>v||'—',(v)=>v||'—',(v)=>'<b>'+v+'</b>',(v)=>'<span class="pill">'+v+'</span>']}));
    }
    drawRange();
    document.getElementById('rvFrom').onchange=drawRange;
    document.getElementById('rvTo').onchange=drawRange;
    document.getElementById('rvPf').onchange=drawRange;
    document.getElementById('rvQ').oninput=drawRange;
    const zbox=document.getElementById('zrTbl');
    function drawZeroRev(){
      const f=document.getElementById('zrFrom').value, t=document.getElementById('zrTo').value, q=document.getElementById('zrQ').value.trim(), pf=document.getElementById('zrPf').value;
      const min=Number(document.getElementById('zrMin').value)||0;
      const m={};
      DATA.detail_rows.forEach(r=>{
        if(f && r.month<f) return;
        if(t && r.month>t) return;
        if(pf && r.platform!==pf) return;
        if(q && !(r.name.includes(q)||r.tid.includes(q))) return;
        const g=m[r.tid]||(m[r.tid]={tid:r.tid,name:r.name,artist:r.artist,plats:{},free:0,pay:0,share:0});
        g.free+=pn(r.free); g.pay+=pn(r.pay); g.share+=Number(r.share)||0; g.plats[r.platform]=1;
      });
      let rows=Object.values(m).filter(g=>(g.free+g.pay)>=min && g.share===0)
        .map(g=>[g.name,g.artist,Object.keys(g.plats).join('/'),fmt(g.free),fmt(g.pay),fmt(g.free+g.pay),'0.00',g.tid]);
      const tf=rows.reduce((s,r)=>s+pn(r[3])||0,0), tp=rows.reduce((s,r)=>s+pn(r[4])||0,0);
      document.getElementById('zrC').textContent='命中 '+rows.length+' 首 ｜ 免费播放合计 '+fmtK(tf)+' ｜ 付费播放合计 '+fmtK(tp)+' ｜ 总播放合计 '+fmtK(tf+tp);
      zbox.innerHTML='';
      zbox.appendChild(sortableTable(['歌曲名称','歌手','平台','免费播放','付费播放','总播放','分成收入(元)','歌曲id'],rows,
        {fmt:[null,null,null,null,null,null,(v)=>'<b>'+v+'</b>',(v)=>'<span class="pill">'+v+'</span>']}));
    }
    drawZeroRev();
    ['zrMin','zrFrom','zrTo','zrPf','zrQ'].forEach(id=>{const e=document.getElementById(id); if(e){e.oninput=drawZeroRev; e.onchange=drawZeroRev;}});
    const lbox=document.getElementById('rvList');
    function drawList(){
      const f=document.getElementById('rvF').value, q=document.getElementById('rvQ2').value.trim();
      let rows=DATA.review_rows.filter(r=>{
        if(f==='risk' && r.risk==='低') return false;
        if(f==='prob' && !(r.tags)) return false;
        if(q && !(r.name.includes(q)||r.tid.includes(q))) return false;
        return true;
      }).map(r=>[r.name,r.artist,r.risk,r.rights,r.aligned,r.tags||'',r.cum_rev,r.tid]);
      document.getElementById('rvC2').textContent='显示 '+rows.length+' 首';
      lbox.innerHTML='';
      lbox.appendChild(sortableTable(['歌曲名称','歌手','版权风险','权利比例','对齐曲库','风险/异常标签','累计分成(元)','歌曲id'],rows,
        {fmt:[null,null,null,null,null,null,(v)=>'<b>'+v+'</b>',(v)=>'<span class="pill">'+v+'</span>']}));
    }
    drawList();
    document.getElementById('rvF').onchange=drawList;
    document.getElementById('rvQ2').oninput=drawList;
  },
  support(){
    const el=document.getElementById('p-support');
    const A=DATA.support_assets||{}, I=DATA.support_info||{};
    const img=(k)=>A[k]?`<img src="${A[k]}" alt="${k}">`:'<div class="muted">（未提供）</div>';
    el.innerHTML=`
    <div class="card">
      <h2><span class="tag">联系合作</span>商务 / 合作联系方式</h2>
      <div class="grid g2" style="margin-top:6px">
        <div class="contact-card">
          <div class="cc-body">
            <div class="cc-title">抖音</div>
            <div class="cc-line">账号：@${I.douyin_name||''}</div>
            <div class="cc-line">抖音号：<b>${I.douyin_id||''}</b></div>
            <div class="cc-line">合作：<b>${I.douyin_coop||''}</b></div>
            <div class="cc-line">扫码，或在抖音搜索抖音号即可私信合作</div>
          </div>
          ${img('douyin')}
        </div>
        <div class="contact-card">
          <div class="cc-body">
            <div class="cc-title">哔哩哔哩</div>
            <div class="cc-line">账号：${I.bilibili_name||''}</div>
            <div class="cc-line">UID：<b>${I.bilibili_uid||''}</b></div>
            <div class="cc-line">扫码，或搜索 UID 找到我</div>
          </div>
          ${img('bilibili')}
        </div>
      </div>
      <div class="note">商务合作请通过抖音私信（抖音号 <b>${I.douyin_id||''}</b>）或 B 站（UID <b>${I.bilibili_uid||''}</b>）联系。</div>
    </div>
    <div class="card">
      <h2><span class="tag">随缘赞助</span>感谢支持</h2>
      <div class="note" style="margin-bottom:14px">看板与工具若对你有帮助，欢迎随缘赞助，金额随意、心意最重要，谢谢支持～</div>
      <div class="qr-grid">
        <div class="qr-card">${img('wechat_pay')}<div class="cap">微信支付 · ${I.wechat_name||''}</div></div>
        <div class="qr-card">${img('alipay')}<div class="cap">支付宝 · ${I.alipay_name||''}</div></div>
        <div class="qr-card">${img('alipay_redpack')}<div class="cap">支付宝领红包 · 天天有优惠</div></div>
      </div>
      <div class="note">二维码均已内嵌在本离线文件中，无需联网即可扫码。</div>
    </div>`;
  }
};

function render(p){ if(renderers[p]) renderers[p](); }
render('overview');
</script>
</body>
</html>
"""

HTML = HTML.replace('__DATA__', json_str)
HTML = HTML.replace('__MONTHS__', ' / '.join(sorted(months_set)))

out = os.path.join(BASE, '汽水数据看板.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(HTML)

print('生成成功:', out)
print('  当日数据:', len(yest_rows), '首  日期', yest_date)
print('  月度结算:', len(monthly_summary), '月  合计', round(total_revenue, 2), '元')
print('  逐歌明细:', len(detail_rows), '行')
print('  歌曲累计:', len(acc_rows), '首')
print('  收入公式: rf/k=%.4f  rp/k=%.4f  付费倍数=%.1f  样本=%d' % (formula['rf_per_k'], formula['rp_per_k'], formula['pay_mult'], formula['n']))
print('  HTML 大小: %.2f MB' % (len(HTML) / 1024 / 1024))
