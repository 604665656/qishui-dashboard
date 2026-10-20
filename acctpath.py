# -*- coding: utf-8 -*-
"""
汽水音乐数据 · 账号隔离辅助模块
================================
解决「换号后数据混在一起」的根因：每个抖音/汽水账号(uid)的数据各存一个子文件夹
  accounts/{uid}/
当前账号记录在 accounts/_current.txt。所有读写都经过本模块，保证不同账号互不串扰。

读取策略 active_account_dir()（看板/筛查优先用当前账号，缺失时回退）：
  1) accounts/{当前uid} 有数据 → 用它
  2) 否则根目录 BASE 有数据 → 回退根目录（部署初期、尚未迁走时）
  3) 否则 accounts/_legacy 有数据 → 回退遗留归档（换号把旧根数据归档后）
  4) 否则返回 accounts/{当前uid}（可能为空，等待首次运行）

迁移策略 migrate_root_to(uid)（仅在 run_update 首次为该账号写数据前调用一次）：
  - 若根目录遗留的 account.json 的 uid 与当前 uid 相同（或无法判定）→ 把根目录数据搬入 accounts/{uid}
  - 若根目录是【另一个账号】的数据 → 归档到 accounts/_legacy，避免串号
"""
import os, sys, json

BASE = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS = os.path.join(BASE, "accounts")
CURRENT_FILE = os.path.join(ACCOUNTS, "_current.txt")

# 需要随账号隔离的数据文件（根目录遗留数据首次运行时迁移）
DATA_FILES = [
    "曲库索引.json", "stats_list.json", "account.json", "overview_1d.json",
    "汽水昨日数据.csv", "收益月度汇总.csv", "收益逐歌明细_全量.csv", "收益逐歌累计.csv",
]
SETTLE_DIR = "结算明细"


def account_dir(uid):
    d = os.path.join(ACCOUNTS, uid or "_unknown")
    os.makedirs(d, exist_ok=True)
    return d


def get_current_uid():
    try:
        if os.path.exists(CURRENT_FILE):
            return open(CURRENT_FILE, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""


def set_current_uid(uid):
    try:
        os.makedirs(ACCOUNTS, exist_ok=True)
        open(CURRENT_FILE, "w", encoding="utf-8").write(uid or "")
    except Exception:
        pass


def _has_data(d):
    if not os.path.isdir(d):
        return False
    for f in DATA_FILES:
        if os.path.exists(os.path.join(d, f)):
            return True
    return False


def active_account_dir():
    """当前应读取的数据目录（见模块 docstring 的回退顺序）。"""
    uid = get_current_uid()
    if uid:
        d = account_dir(uid)
        if _has_data(d):
            return d
    if _has_data(BASE):
        return BASE
    # uid 为空时也优先取某个已有账号目录，避免读写错位（写去 accounts/{uid} 却读 _legacy）
    try:
        for name in sorted(os.listdir(ACCOUNTS)):
            if name == "_legacy":
                continue
            d = os.path.join(ACCOUNTS, name)
            if _has_data(d):
                return d
    except Exception:
        pass
    leg = os.path.join(ACCOUNTS, "_legacy")
    if _has_data(leg):
        return leg
    if uid:
        return account_dir(uid)
    return BASE


def _archive_root():
    """把根目录遗留数据归档到 accounts/_legacy（不动音乐/歌词媒体目录）。"""
    leg = account_dir("_legacy")
    moved = False
    for f in DATA_FILES:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            try:
                os.replace(src, os.path.join(leg, f)); moved = True
            except Exception:
                pass
    sd = os.path.join(BASE, SETTLE_DIR)
    dd = os.path.join(leg, SETTLE_DIR)
    if os.path.isdir(sd):
        try:
            os.makedirs(dd, exist_ok=True)
            for fn in os.listdir(sd):
                s2 = os.path.join(sd, fn)
                if os.path.isfile(s2):
                    os.replace(s2, os.path.join(dd, fn)); moved = True
            if not os.listdir(sd):
                os.rmdir(sd)
        except Exception:
            pass
    return moved


def migrate_root_to(uid):
    """首次为某账号写数据前调用：把根目录遗留数据迁入 accounts/{uid}（同账号）或归档（异账号）。
    返回是否发生了移动/归档。"""
    d = account_dir(uid)
    if _has_data(d):
        return False  # 该账号已有数据，跳过
    root_uid = ""
    try:
        a = json.load(open(os.path.join(BASE, "account.json"), encoding="utf-8"))
        root_uid = a.get("uid", "")
    except Exception:
        pass
    if root_uid and root_uid != uid:
        # 根目录是另一个账号 → 归档，避免串号
        _archive_root()
        return True
    # 同账号或无法判定 → 迁入当前账号目录
    moved = False
    for f in DATA_FILES:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            try:
                os.replace(src, os.path.join(d, f)); moved = True
            except Exception:
                pass
    sd = os.path.join(BASE, SETTLE_DIR)
    dd = os.path.join(d, SETTLE_DIR)
    if os.path.isdir(sd):
        try:
            os.makedirs(dd, exist_ok=True)
            for fn in os.listdir(sd):
                s2 = os.path.join(sd, fn)
                if os.path.isfile(s2):
                    os.replace(s2, os.path.join(dd, fn)); moved = True
            if not os.listdir(sd):
                os.rmdir(sd)
        except Exception:
            pass
    return moved
