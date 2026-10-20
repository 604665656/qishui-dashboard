# -*- coding: utf-8 -*-
"""
临时从 accounts/_legacy 重建看板（方案 B）
========================================
用途：当前登录账号(6df7...)查不到结算单、收益为空时，让用户立即看到【旧账号】的
付费播放量 / 付费收入 / 分成收入 / 逐歌明细 / 版权排查 等历史付费数据。

原理：build_dashboard.py 与 review_songs.py 都在导入时通过
acctpath.active_account_dir() 决定数据目录。本脚本在导入它们【之前】
把该函数替换为返回 accounts/_legacy，从而让看板从归档数据生成。

产物：汽水数据看板_旧账号付费数据.html （独立文件名，不覆盖当前账号看板）
注意：这仅是「临时查看」，不改变任何账号状态；登对正确账号后重跑 update_all.py
即可刷新回当前账号的看板。
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
LEGACY = os.path.join(BASE, "accounts", "_legacy")

import acctpath
# 关键：在 build_dashboard / review_songs 导入前，让 active_account_dir 指向归档
if not os.path.isdir(LEGACY):
    print("未找到 accounts/_legacy 归档目录，无法重建历史看板。")
    sys.exit(1)
acctpath.active_account_dir = lambda: LEGACY

# 导入即执行：build_dashboard 会读取 legacy 的 CSV 并写出 汽水数据看板.html
import build_dashboard

src = os.path.join(BASE, "汽水数据看板.html")
dst = os.path.join(BASE, "汽水数据看板_旧账号付费数据.html")
if os.path.exists(src):
    os.replace(src, dst)
    print("已生成历史付费数据看板:", dst)
else:
    print("看板文件未生成，请检查 legacy 数据完整性。")
