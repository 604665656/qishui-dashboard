# -*- coding: utf-8 -*-
"""
汽水音乐 · 歌曲版权风险 & 收益异常 一键排查
==========================================
基于本地已抓取数据，对每首歌做「版权风险」与「收益异常」筛查。

筛查维度（全部来自平台返回的本地数据，非平台官方"版权状态"字段）：
  1) 权利比例：录音/词/曲 是否 100% 自有。
     - 三者全 0  → 零权利（高度疑似非本人作品，风险高）
     - 任一 <100 → 权利不全（协作/代发/ others 持有部分权利，风险中）
     - 全 100%  → 完全自有（风险低）
  2) 对齐曲库：收益歌曲是否在本地曲库索引中（否 → 未核对/疑非本人作品）
  3) 收益异常：
     - 零播放有收益：汽水播放合计=0 但 分成>0
     - 高播放零收益：汽水播放合计≥3000 但 分成=0（可能结算滞后或权利问题）
     - 未入库却有收益：对齐曲库=否 且 累计分成>0

重要说明：
  · 平台创作者后台【不提供】单曲"是否侵权/是否授权"的官方字段。
  · 本工具只能基于本地「权利比例 / 对齐曲库 / 收益」做辅助筛查，
    不能替代法律意见，也不能作为官方确权依据。
  · 「对齐曲库」依赖 曲库索引.json；若当前账号已换号而索引未重建，
    该列会失效（详见运行末尾提示）。

用法：
  python review_songs.py                # 生成 歌曲风险排查表.csv + 打印摘要
  python review_songs.py --id 764377...  # 按歌曲id查询
  python review_songs.py --name 关键词   # 按名称/演唱者关键词查询
"""
import csv, json, os, sys, re, argparse
from collections import Counter
import acctpath  # 账号隔离：读当前账号数据目录

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)          # EXE 单文件：数据在同目录
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# 当前账号数据目录（accounts/{uid}；首次未迁走时回退根目录/ _legacy）
DATA_DIR = acctpath.active_account_dir()

def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def parse_rights(s):
    """'录音0%/词50%/曲0%' -> (rec, lyric, comp) 浮点百分比"""
    d = {'录音': 0.0, '词': 0.0, '曲': 0.0}
    for k, v in re.findall(r'(录音|词|曲)\s*(\d+(?:\.\d+)?)\s*%', s or ''):
        d[k] = float(v)
    return d['录音'], d['词'], d['曲']

def load_library():
    path = os.path.join(DATA_DIR, '曲库索引.json')
    lib = {}
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                for it in json.load(f):
                    lib[str(it.get('track_id'))] = it
        except Exception:
            pass
    return lib

def analyze():
    detail = read_csv(os.path.join(DATA_DIR, '收益逐歌明细_全量.csv'))
    cum    = read_csv(os.path.join(DATA_DIR, '收益逐歌累计.csv'))
    lib    = load_library()

    songs = {}
    for r in detail:
        tid = r['歌曲id']
        s = songs.setdefault(tid, {
            'tid': tid, 'name': r['歌曲名称'], 'artist': r['歌手名称'],
            'rights': r['权利比例'], 'aligned': '否',
            'rev_total': 0.0, 'play_free': 0.0, 'play_paid': 0.0,
            'months_with_rev': set(), 'plat_rev': {},
        })
        rev = num(r['分成收入'])
        s['rev_total'] += rev
        if r['对齐曲库'] == '是':
            s['aligned'] = '是'
        if r['平台'] == '汽水音乐':
            s['play_free'] += num(r['免费播放量'])
            s['play_paid'] += num(r['付费播放量'])
        if rev > 0:
            s['months_with_rev'].add(r['月份'])
        s['plat_rev'][r['平台']] = s['plat_rev'].get(r['平台'], 0.0) + rev

    cum_map = {r['歌曲id']: r for r in cum}

    rows = []
    for tid, s in songs.items():
        rec, ly, comp = parse_rights(s['rights'])
        all100 = rec == 100 and ly == 100 and comp == 100
        zero_r = rec == 0 and ly == 0 and comp == 0
        if zero_r:
            risk, risk_reason = '高', '零权利(录音0/词0/曲0,疑似他人作品)'
        elif not all100:
            risk, risk_reason = '中', f'权利不全(录音{rec:.0f}%/词{ly:.0f}%/曲{comp:.0f}%)'
        else:
            risk, risk_reason = '低', '完全自有(录音/词/曲均100%)'

        tags = []
        if risk == '高':
            tags.append('版权高风险-零权利')
        elif risk == '中':
            tags.append('版权中风险-权利不全')
        if s['aligned'] == '否':
            tags.append('未在曲库')
        plays = s['play_free'] + s['play_paid']
        if plays == 0 and s['rev_total'] > 0:
            tags.append('零播放有收益')
        if plays >= 3000 and s['rev_total'] == 0:
            tags.append('高播放零收益')
        if s['aligned'] == '否' and s['rev_total'] > 0:
            tags.append('未入库却有收益')

        c = cum_map.get(tid)
        cum_rev = num(c['累计分成收入(元)']) if c else s['rev_total']
        nmonths = c['有收益月份数'] if c else len(s['months_with_rev'])

        rows.append({
            'tid': tid, 'name': s['name'], 'artist': s['artist'],
            'risk': risk, 'risk_reason': risk_reason, 'rights': s['rights'],
            'aligned': s['aligned'], 'cum_rev': cum_rev, 'nmonths': nmonths,
            'plays': plays, 'tags': ';'.join(tags),
        })
    # 排序：高/中风险优先，其次按累计收益降序
    rows.sort(key=lambda x: (x['risk'] != '高', x['risk'] != '中', -x['cum_rev']))
    return rows, lib

def build_report(rows):
    out = os.path.join(BASE, '歌曲风险排查表.csv')
    cols = ['歌曲id', '歌曲名称', '演唱者', '版权风险', '权利比例', '对齐曲库',
            '累计分成收入(元)', '有收益月份数', '汽水播放量', '风险标签']
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r['tid'], r['name'], r['artist'], r['risk'], r['rights'],
                        r['aligned'], f"{r['cum_rev']:.2f}", r['nmonths'],
                        f"{r['plays']:.0f}", r['tags']])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', help='按歌曲id查询')
    ap.add_argument('--name', help='按歌曲名称/演唱者关键词查询')
    args = ap.parse_args()

    rows, lib = analyze()

    if args.id or args.name:
        q = args.id or args.name
        hit = [r for r in rows if q in (r['tid'] + r['name'] + r['artist'])]
        if not hit:
            print('未找到匹配:', q)
        for r in hit:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        return

    out = build_report(rows)
    rc = Counter(r['risk'] for r in rows)
    tc = Counter()
    for r in rows:
        for t in r['tags'].split(';'):
            if t:
                tc[t] += 1
    print('已生成:', out)
    print('歌曲总数:', len(rows))
    print('版权风险分布:', dict(rc))
    print('风险/异常标签分布:', dict(tc))
    print('曲库索引条目数:', len(lib))
    print('【提示】若「未在曲库」标签数量异常偏高，通常是因为 曲库索引.json 仍停留在'
          '旧账号（换号未隔离）。该列失效期间，仅「权利比例」维度可靠。')

if __name__ == '__main__':
    main()
