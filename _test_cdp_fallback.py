# -*- coding: utf-8 -*-
"""验证：当 C:\\edge-cdp 不可写（别人电脑常见）时，profile 目录是否回退到用户目录。"""
import os, sys
sys.argv = ['x']

_real_access = os.access
_real_isdir = os.path.isdir


def fake_access(p, m):
    if os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath("C:\\edge-cdp")):
        return False
    return _real_access(p, m)


os.access = fake_access
import update_all as UA
print("模拟无 C:\\edge-cdp 权限 ->", UA.CDP_USER_DATA)

os.access = _real_access
import importlib
importlib.reload(UA)
print("正常情况 ->", UA.CDP_USER_DATA)
print("探测到的浏览器:", UA.find_browsers())
