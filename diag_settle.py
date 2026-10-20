# -*- coding: utf-8 -*-
"""诊断：当前登录账号的结算月份接口是否真的无数据（区分代码 bug 与账号无结算）"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_all as UA

ck, ckm = UA.get_cookies()
uid = UA.get_account_uid(ckm)
print("当前 uid:", uid)
print("是否取到 Cookie:", bool(ck))
if not ck:
    print("→ CDP/ Cookie 不可用，无法诊断在线接口。")
    sys.exit(0)

API = "https://music.douyin.com/console/api/v1/settlement/statement"
for ep in ("/period_range",):
    try:
        pr = UA.py_get(API + ep, ck)
        print(ep, "baseResp:", json.dumps(pr.get("baseResp", {}), ensure_ascii=False))
        print(ep, "data(前600):", json.dumps(pr.get("data", {}), ensure_ascii=False)[:600])
    except Exception as e:
        print(ep, "异常:", repr(e))

# 也试一下不带 /console 的另一种常见前缀，排查是否接口路径变了
for alt in ("https://music.douyin.com/api/v1/settlement/statement/period_range",):
    try:
        pr = UA.py_get(alt, ck)
        print("ALT", alt, "baseResp:", json.dumps(pr.get("baseResp", {}), ensure_ascii=False))
        print("ALT data(前400):", json.dumps(pr.get("data", {}), ensure_ascii=False)[:400])
    except Exception as e:
        print("ALT", alt, "异常:", repr(e))
