# -*- coding: utf-8 -*-
"""把联系/赞助二维码压缩并 base64 内嵌为 contact_assets.py（离线看板自包含）。"""
import base64, io, os
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\60466\.workbuddy\clipboard-images"

FILES = [
    ("alipay_redpack", "clipboard-2026-10-20T06-40-11-018Z-aed66f48.png", "支付宝领红包"),
    ("wechat_pay",     "clipboard-2026-10-20T06-40-11-023Z-bea70404.jpg", "微信支付"),
    ("douyin",         "clipboard-2026-10-20T06-40-11-023Z-7acad140.jpg", "抖音"),
    ("bilibili",       "clipboard-2026-10-20T06-40-11-024Z-1acaa037.jpg", "哔哩哔哩"),
    ("alipay",         "clipboard-2026-10-20T06-40-11-025Z-90f2e3f4.jpg", "支付宝"),
]

MAXW = 460  # 目标最大宽度（QR 仍可扫）

def encode(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    w, h = im.size
    if w > MAXW:
        im = im.resize((MAXW, int(h * MAXW / w)), Image.LANCZOS)
    # 纯二维码类用 PNG（无损、保证可扫）；装饰图用 JPEG 省体积
    is_qr = ("二维码" in "") or True
    buf = io.BytesIO()
    # 统一 PNG，保证二维码清晰
    im.save(buf, format="PNG", optimize=True)
    b = buf.getvalue()
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii"), len(b)

assets = {}
total = 0
for key, fn, label in FILES:
    p = os.path.join(SRC, fn)
    uri, n = encode(p)
    assets[key] = uri
    total += n
    print(f"{key:16s} {label:8s} {n/1024:7.1f} KB  png")

INFO = {
    "douyin_name": "许许许许许丶若辰",
    "douyin_id": "A604665656",
    "douyin_coop": "A604665656",
    "bilibili_name": "许许许许许丶若辰",
    "bilibili_uid": "298813",
    "wechat_name": "许楷风（**风）",
    "alipay_name": "楷风（**风）",
}

out = os.path.join(BASE, "contact_assets.py")
with open(out, "w", encoding="utf-8") as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write('"""联系合作 / 赞助二维码（base64 内嵌，自动生成，勿手改）。"""\n\n')
    f.write("ASSETS = {\n")
    for k, v in assets.items():
        f.write(f"    {k!r}: {v!r},\n")
    f.write("}\n\nINFO = ")
    import pprint
    f.write(pprint.pformat(INFO, width=120, sort_dicts=False))
    f.write("\n")

print(f"\n总图片体积: {total/1024:.1f} KB (PNG)")
print("已生成:", out, os.path.getsize(out)/1024, "KB")
