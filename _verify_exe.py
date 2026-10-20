# -*- coding: utf-8 -*-
"""校验打包后的 EXE 是否真的含新逻辑。
扫两类信息：
  1) 字符串常量（co_consts）—— 路径、提示文案等
  2) 标识符（co_name / co_names / 局部变量名）—— 函数名等（函数名不会以字符串常量形式存储）
"""
import sys, marshal
from PyInstaller.archive.readers import CArchiveReader

KEYS = [
    "find_browsers",            # 多浏览器探测
    "cdp_manual_hint",          # 新提示
    "_try_launch_cdp",
    "launch_app_window",
    "QishuiCDP",                # profile 目录回退
    "remote-allow-origins",
    "chrome.exe",
    "QQBrowser.exe",
    "360chrome.exe",
    "App Paths",                # 注册表探测
    "未能自动启动专用浏览器",
]


def _match(text, hits):
    for k in KEYS:
        if k in text:
            hits[k] += 1


def walk(code, hits, seen=None):
    if seen is None:
        seen = set()
    if id(code) in seen:
        return
    seen.add(id(code))
    try:
        _match(code.co_name, hits)
        for n in code.co_names:
            _match(n, hits)
        for n in code.co_varnames:
            _match(n, hits)
    except Exception:
        pass
    for c in code.co_consts:
        if isinstance(c, str):
            _match(c, hits)
        elif isinstance(c, bytes):
            try:
                _match(c.decode("utf-8", "ignore"), hits)
            except Exception:
                pass
        elif hasattr(c, "co_consts"):
            walk(c, hits, seen)


def feed(obj, hits):
    if isinstance(obj, bytes):
        for skip in (0, 16, 12, 8):
            try:
                obj = marshal.loads(obj[skip:])
                break
            except Exception:
                continue
        else:
            return
    if hasattr(obj, "co_consts"):
        walk(obj, hits)


def scan(path):
    ar = CArchiveReader(path)
    hits = {k: 0 for k in KEYS}
    for name in ar.toc:                      # 主脚本 + 运行时模块
        try:
            feed(ar.extract(name), hits)
        except Exception:
            continue
    try:                                     # PYZ 内的依赖
        inner = ar.open_embedded_archive("PYZ.pyz")
        for name in inner.toc:
            try:
                feed(inner.extract(name), hits)
            except Exception:
                continue
    except Exception as e:
        print("  (PYZ skip:", e, ")")

    print("=" * 62)
    print(path)
    for k in KEYS:
        print("   %-26s %d" % (k, hits[k]))
    missing = [k for k in KEYS if hits[k] == 0]
    print("   =>", "全部命中 OK" if not missing else "缺失: %s" % missing)
    return not missing


ok = True
for p in sys.argv[1:]:
    ok = scan(p) and ok
sys.exit(0 if ok else 1)
