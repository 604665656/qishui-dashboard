# -*- coding: utf-8 -*-
"""
汽水音乐数据 · 一键更新脚本（无需模型 TOKEN）
==========================================
一键刷新全部本地数据并重建看板：
  1) 刷新「昨日汽水播放/热度」(disclosure/overview period=1)
  2) 自动发现并下载所有已结算月份的「逐歌收益明细」(settlement/statement/download)
  3) 重建 收益月度汇总 / 收益逐歌明细_全量 / 收益逐歌累计 三张表
  4) 调用 build_dashboard.py 重建 汽水数据看板.html

实现：通过 CDP 从已登录 Edge 提取 Cookie，其余接口全部由 Python 直连（绕过浏览器代理）。
前置：本机已用 CDP 启动并登录的 Edge（默认端口 9222，user-data-dir=C:\\edge-cdp）。
若 9222 未开，脚本会给出启动命令后退出。

账号/登录封装：
  - 首次使用（缺 曲库索引.json）、在另一台机器、或检测到 Cookie 账号与上次不同（uid 变化），
    会自动抓取当前登录账号的歌单并生成 曲库索引.json / stats_list.json，无需手动准备清单。
  - 手动强制重新抓取歌单（换号后想保留旧数据另存时）：python update_all.py --reinit

用法：python update_all.py [--reinit]
"""
import json, os, sys, time, datetime, csv, tempfile, urllib.request, urllib.error, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import acctpath  # 账号隔离：accounts/{uid}/

BASE = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
         else os.path.dirname(os.path.abspath(__file__)))
ACCT_DIR = BASE  # 当前账号数据目录；run_update 取得 uid 后会重设为 accounts/{uid}
PORT = 9222                      # 首选调试端口
CDP_PORTS = [9222, 9223, 9333]   # 端口被占用时依次尝试
_ACTIVE_PORT = [PORT]            # 当前实际在用的端口（可变）


def cdp_http(port=None):
    return "http://127.0.0.1:%d" % (port or _ACTIVE_PORT[0])


CDP_HTTP = cdp_http()            # 兼容旧引用
SETTLE_API = "https://music.douyin.com/console/api/v1/settlement/statement"
DETAIL_DIR = os.path.join(BASE, "结算明细")  # run_update 会按账号重设并创建


# 专用浏览器（CDP）配置：登录/退出都作用于这个独立 profile
def _default_cdp_user_data():
    """挑一个当前用户一定写得进的 profile 目录。
    旧版固定 C:\\edge-cdp，很多电脑（无管理员权限 / C 盘根目录受限）创建失败，
    导致『未能启动专用浏览器』。这里：旧目录已存在且可写就沿用（保住旧登录态），
    否则退到 %LOCALAPPDATA%\\QishuiCDP。"""
    old = r"C:\edge-cdp"
    try:
        if os.path.isdir(old) and os.access(old, os.W_OK):
            return old
    except Exception:
        pass
    base = (os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            or tempfile.gettempdir())
    return os.path.join(base, "QishuiCDP")


CDP_USER_DATA = _default_cdp_user_data()
LOGIN_URL = "https://music.douyin.com/"  # 汽水音乐网页版（直接展示扫码登录二维码）
ACCOUNT_JSON = os.path.join(BASE, "account.json")

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PY = sys.executable
LOG = []

def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)


def http_get_json(path, port=None, timeout=8):
    return json.loads(urllib.request.urlopen(cdp_http(port) + path, timeout=timeout).read())


def discover_ws(port=None):
    try:
        return http_get_json("/json/version", port, timeout=3).get("webSocketDebuggerUrl")
    except Exception:
        return None


def active_cdp_port():
    """扫描候选端口，返回已经开着的 CDP 端口；没有则 None。"""
    for p in CDP_PORTS:
        if discover_ws(p):
            _ACTIVE_PORT[0] = p
            return p
    return None


# ---------------- 浏览器探测：Edge / Chrome / Chromium / Brave / 360 / QQ 等 ----------------
def _reg_app_path(exe_name):
    """从注册表 App Paths 读浏览器真实安装路径（比硬编码可靠）。"""
    try:
        import winreg
    except Exception:
        return None
    subs = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe_name),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe_name),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe_name),
    ]
    for root, sub in subs:
        try:
            with winreg.OpenKey(root, sub) as k:
                val, _ = winreg.QueryValueEx(k, "")
                if val and os.path.exists(val):
                    return val
        except Exception:
            continue
    return None


def find_browsers():
    """按优先级返回本机可用的 Chromium 内核浏览器 [(显示名, 路径), ...]。
    顺序：注册表查到的 → 常见安装路径（Edge → Chrome → Chromium/Brave → 国产）。"""
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    out, seen = [], set()
    for label, exe in (("Edge", "msedge.exe"), ("Chrome", "chrome.exe"),
                       ("Brave", "brave.exe"), ("Chromium", "chromium.exe"),
                       ("QQ浏览器", "QQBrowser.exe"), ("360极速浏览器", "360chrome.exe")):
        p = _reg_app_path(exe)
        if p:
            out.append((label, p)); seen.add(p.lower())
    fixed = [
        ("Edge", os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe")),
        ("Edge", os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe")),
        ("Edge", os.path.join(local, r"Microsoft\Edge\Application\msedge.exe")),
        ("Chrome", os.path.join(pf, r"Google\Chrome\Application\chrome.exe")),
        ("Chrome", os.path.join(pf86, r"Google\Chrome\Application\chrome.exe")),
        ("Chrome", os.path.join(local, r"Google\Chrome\Application\chrome.exe")),
        ("Chromium", os.path.join(local, r"Chromium\Application\chrome.exe")),
        ("Brave", os.path.join(pf, r"BraveSoftware\Brave-Browser\Application\brave.exe")),
        ("Brave", os.path.join(local, r"BraveSoftware\Brave-Browser\Application\brave.exe")),
        ("360极速浏览器", os.path.join(local, r"360Chrome\Chrome\Application\360chrome.exe")),
        ("QQ浏览器", os.path.join(pf86, r"Tencent\QQBrowser\QQBrowser.exe")),
        ("QQ浏览器", os.path.join(pf, r"Tencent\QQBrowser\QQBrowser.exe")),
    ]
    for label, p in fixed:
        if p and p.lower() not in seen and os.path.exists(p):
            out.append((label, p)); seen.add(p.lower())
    return out


def cdp_manual_hint():
    """手动启动专用浏览器的命令提示（按本机实际探测到的浏览器给出）。"""
    bs = find_browsers()
    if not bs:
        return ("未在本机找到 Chrome / Edge 等 Chromium 内核浏览器。"
                "请先安装 Edge 或 Chrome，再重试。")
    lines = ["未能自动启动专用浏览器。请任选下面一条命令，复制到「运行」(Win+R) 执行："]
    for label, p in bs[:3]:
        lines.append('  [%s] "%s" --remote-debugging-port=%d --user-data-dir="%s"'
                     % (label, p, _ACTIVE_PORT[0], CDP_USER_DATA))
    lines.append("浏览器打开后，再回到本工具点【登录账号】。")
    return "\n".join(lines)


# ---------------- CDP 仅用于取 Cookie ----------------
def get_cookies():
    ws_url = discover_ws()
    if not ws_url and active_cdp_port():   # 端口换过（9222 被占用）时再确认一次
        ws_url = discover_ws()
    if not ws_url:
        return None, {}
    from websocket import create_connection
    tabs = http_get_json("/json")
    page = next((t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
    if not page:
        return None, {}
    ws = create_connection(page["webSocketDebuggerUrl"], timeout=30)
    n = [0]
    def send(m, p=None):
        n[0] += 1; i = n[0]; ws.send(json.dumps({"id": i, "method": m, "params": p or {}})); return i
    def recvid(i, t=20):
        e = time.time()
        while time.time() - e < t:
            try: r = json.loads(ws.recv())
            except Exception: return None
            if r.get("id") == i: return r
    send("Network.enable"); time.sleep(0.3)
    r = recvid(send("Network.getAllCookies"), 15)
    ws.close()
    cookies = (r.get("result", {}).get("cookies", [])) if r else []
    ck = "; ".join(f"{c['name']}={c['value']}" for c in cookies
                   if "douyin" in c.get("domain", "") or "bytedance" in c.get("domain", ""))
    ckm = {c["name"]: c["value"] for c in cookies}
    return (ck or None), ckm


def get_account_uid(ckm):
    return ckm.get("uid_tt_ss") or ckm.get("uid_tt") or ""


# ---------------- 账号登录 / 退出（CDP 辅助） ----------------
def _port_busy(port):
    """端口是否被某个已在监听的程序占用（但那不是 CDP）。"""
    try:
        import socket
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except Exception:
        return False


def _try_launch_cdp(exe, port, open_url=None, wait=10):
    """尝试用某个浏览器打开调试端口，成功返回 True。"""
    args = [exe, "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % CDP_USER_DATA,
            "--remote-allow-origins=*",
            "--no-first-run", "--no-default-browser-check"]
    if open_url:
        args.append(open_url)
    try:
        proc = subprocess.Popen(args)
    except Exception:
        return False
    for _ in range(wait):
        time.sleep(1)
        if discover_ws(port):
            return True
    try:
        proc.terminate()   # 这个浏览器没起来，换下一个
    except Exception:
        pass
    return False


def ensure_cdp_edge(open_url=None, wait=10):
    """确认专用浏览器(CDP)是否已启动；未启动则依次尝试本机可用的
    Edge / Chrome / Chromium / Brave / 360 / QQ 浏览器，用独立 profile 打开调试端口。
    返回 True 表示 CDP 可用。"""
    if active_cdp_port():
        return True
    bs = find_browsers()
    if not bs:
        return False
    for port in CDP_PORTS:                 # 端口被别的软件占用时换一个
        if _port_busy(port):               # 端口已被非 CDP 程序占用，别浪费时间等
            continue
        for label, exe in bs:
            if _try_launch_cdp(exe, port, open_url, wait):
                _ACTIVE_PORT[0] = port
                return True
    return False


def launch_app_window(url):
    """用 --app 模式打开一个无地址栏窗口（看板界面用），多浏览器兜底。"""
    for label, exe in find_browsers():
        try:
            subprocess.Popen([exe, "--app=%s" % url, "--window-size=1280,860"])
            return True
        except Exception:
            continue
    try:
        import webbrowser
        webbrowser.open(url)
        return False
    except Exception:
        return False


def cdp_open_tab(url):
    """在专用浏览器中新建一个标签页打开指定 URL（用于登录引导）。"""
    ws_url = discover_ws()
    if not ws_url:
        return False
    from websocket import create_connection
    ws = create_connection(ws_url, timeout=30)
    try:
        ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": url}}))
        for _ in range(40):
            try:
                r = json.loads(ws.recv())
            except Exception:
                break
            if r.get("id") == 1:
                break
        return True
    finally:
        ws.close()


def cdp_clear_account_cookies(extra_domains=None):
    """清除专用浏览器中汽水/抖音/字节系 Cookie（退出登录）。返回清除条数。
    extra_domains 仅供测试：额外纳入清除的域名。"""
    try:
        tabs = http_get_json("/json")
    except Exception:
        return 0
    page = next((t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
    if not page:
        return 0
    from websocket import create_connection
    ws = create_connection(page["webSocketDebuggerUrl"], timeout=30)
    try:
        nid = [0]
        def send(m, p=None):
            nid[0] += 1; i = nid[0]
            ws.send(json.dumps({"id": i, "method": m, "params": p or {}})); return i
        def recvid(i, t=15):
            e = time.time()
            while time.time() - e < t:
                try:
                    r = json.loads(ws.recv())
                except Exception:
                    return None
                if r.get("id") == i:
                    return r
        send("Network.enable"); time.sleep(0.3)
        r = recvid(send("Network.getAllCookies"))
        cookies = (r.get("result", {}).get("cookies", [])) if r else []
        keep = ("douyin", "bytedance", "toutiao", "pangle") + tuple(extra_domains or ())
        dom = {c.get("domain", "") for c in cookies if any(k in c.get("domain", "") for k in keep)}
        deleted = 0
        for c in cookies:
            if c.get("domain", "") in dom:
                recvid(send("Network.deleteCookies",
                            {"name": c["name"], "domain": c["domain"], "path": c.get("path", "/")}))
                deleted += 1
        return deleted
    finally:
        ws.close()


def reset_account_state():
    """重置本地账号记录（account.json），下次更新会按 uid 变化重新引导。"""
    try:
        p = os.path.join(ACCT_DIR, "account.json")
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


def login_account():
    """拉起/复用专用浏览器并打开登录页。返回是否成功连接浏览器。"""
    if not ensure_cdp_edge():
        return False
    cdp_open_tab(LOGIN_URL)
    return True


def logout_account():
    """退出当前账号：清除浏览器登录态 + 重置本地账号记录。返回 (浏览器可用, 清除条数)。"""
    if ensure_cdp_edge():
        n = cdp_clear_account_cookies()
        reset_account_state()
        return True, n
    reset_account_state()
    return False, 0


# ---------------- Python 直连接口 ----------------
def py_get(url, cookies, is_json=True, timeout=25):
    req = urllib.request.Request(url, headers={
        "Cookie": cookies, "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.douyin.com/console/settlement/index"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        txt = resp.read().decode("utf-8", "replace")
    return json.loads(txt) if is_json else txt


# ---------------- 引导：抓取当前账号歌单 ----------------
SONG_LIST_API = "https://music.douyin.com/api/statistics/disclosure/songs"

def bootstrap_catalog(cookies, ckm):
    """抓取当前登录账号的全部歌曲清单，生成 stats_list.json 与 曲库索引.json。
    纯 Cookie 直连即可（无需 a_bogus 签名）；pageSize 固定=10，故并发翻页。"""
    log("\n[1/5] 引导：抓取当前账号歌单（首次使用 / 换账号）...")
    acc_uid = get_account_uid(ckm)

    def fetch_page(p):
        url = f"{SONG_LIST_API}?songType=1&songForm=1&currentPage={p}&pageSize=10"
        for _ in range(3):
            try:
                j = py_get(url, cookies, is_json=True, timeout=20)
                d = j.get("data", {})
                if j.get("baseResp", {}).get("errorCode") == 0:
                    return p, d.get("total"), d.get("songs", [])
            except Exception:
                time.sleep(0.3)
        return p, None, []

    p1, total, s1 = fetch_page(1)
    if total is None:
        log("    !! 歌单首页抓取失败（Cookie 可能失效，请在 Edge 重新登录后台）")
        return 0
    try:
        total = int(total)
    except Exception:
        total = len(s1)
    pages = (total + 9) // 10
    log(f"    共 {total} 首，需翻 {pages} 页（并发 20）")
    by_page = {1: s1}
    if pages > 1:
        done = 0
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = {ex.submit(fetch_page, p): p for p in range(2, pages + 1)}
            for f in as_completed(futs):
                p, _, songs = f.result()
                if songs:
                    by_page[p] = songs
                done += 1
                if done % 50 == 0:
                    log(f"    进度 {done}/{pages - 1} 页")
    all_songs = []
    for p in sorted(by_page):
        all_songs.extend(by_page[p])
    # 去重（按 metaSongId）
    seen, uniq = set(), []
    for s in all_songs:
        mid = s.get("metaSongId")
        if mid and mid not in seen:
            seen.add(mid); uniq.append(s)
    all_songs = uniq
    log(f"    抓取去重后：{len(all_songs)} 首")

    # 保留已有音乐下载状态（file/ok/bytes/duration）
    lib_path = os.path.join(ACCT_DIR, "曲库索引.json")
    old_map = {}
    if os.path.exists(lib_path):
        try:
            for it in json.load(open(lib_path, encoding="utf-8")):
                old_map[it.get("track_id")] = it
        except Exception:
            pass
    maxseq = 0
    for it in old_map.values():
        try:
            maxseq = max(maxseq, int(str(it.get("file", "")).split("-")[0]))
        except Exception:
            pass
    lib, seq = [], maxseq
    for s in all_songs:
        tid = str(s.get("metaSongId", ""))
        old = old_map.get(tid)
        if old:
            rec = dict(old)
            rec["title"] = s.get("title", "") or old.get("title", "")
            rec["artist"] = s.get("artistName", "") or old.get("artist", "")
            rec["track_id"] = tid
        else:
            seq += 1
            rec = {"title": s.get("title", ""), "artist": s.get("artistName", ""),
                   "track_id": tid, "duration": 0, "file": f"{seq:04d}-{s.get('title', '')}",
                   "ok": False, "bytes": 0}
        lib.append(rec)

    json.dump({"total": total, "done_pages": pages, "songs": all_songs},
              open(os.path.join(ACCT_DIR, "stats_list.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(lib, open(lib_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"uid": acc_uid, "bootstrap_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "total": total},
              open(os.path.join(ACCT_DIR, "account.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"    已生成 曲库索引.json({len(lib)} 首) / stats_list.json / account.json(uid={acc_uid})")
    return len(lib)


def need_bootstrap(ckm):
    """判断是否需要先引导：文件缺失 / 账号切换 / 手动 --reinit"""
    reasons = []
    if "--reinit" in sys.argv:
        reasons.append("手动 --reinit")
    lib_path = os.path.join(ACCT_DIR, "曲库索引.json")
    if not os.path.exists(lib_path):
        reasons.append("曲库索引.json 缺失（首次使用 / 新机器）")
    else:
        uid = get_account_uid(ckm)
        try:
            acc = json.load(open(os.path.join(ACCT_DIR, "account.json"), encoding="utf-8"))
            old_uid = acc.get("uid", "")
            if uid and old_uid and old_uid != uid:
                reasons.append(f"检测到账号切换（旧 {old_uid} → 新 {uid}）")
        except Exception:
            pass
    return reasons


def load_song_ids():
    try:
        d = json.load(open(os.path.join(ACCT_DIR, "stats_list.json"), encoding="utf-8"))
        ids = [s["metaSongId"] for s in d.get("songs", []) if s.get("metaSongId")]
        if ids:
            return ids
    except Exception:
        pass
    lib = json.load(open(os.path.join(ACCT_DIR, "曲库索引.json"), encoding="utf-8"))
    return [it["track_id"] for it in lib]


def refresh_yesterday(cookies):
    log("\n[2/5] 刷新昨日汽水播放/热度 (period=1) ...")
    ids = load_song_ids()
    metrics, date = {}, None
    libmap = {}
    try:
        lib = json.load(open(os.path.join(ACCT_DIR, "曲库索引.json"), encoding="utf-8"))
        for it in lib:
            libmap[it["track_id"]] = (it.get("song_name") or it.get("歌名") or it.get("title") or "",
                                      it.get("artist") or it.get("作者") or it.get("singer") or "")
    except Exception:
        pass

    def fetch_one(sid):
        url = f"https://music.douyin.com/api/statistics/disclosure/overview?scope=2&songID={sid}&period=1"
        for _ in range(3):
            try:
                j = py_get(url, cookies, is_json=True, timeout=15)
                if j.get("baseResp", {}).get("errorCode") == 0 and j.get("data", {}).get("metrics"):
                    m = {str(x["metricType"]): x["value"] for x in j["data"]["metrics"]}
                    return sid, m, j["data"].get("updateTime")
            except Exception:
                time.sleep(0.5)
        return sid, None, None

    done = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(fetch_one, sid): sid for sid in ids}
        for f in as_completed(futs):
            sid, m, ut = f.result()
            if m:
                metrics[sid] = m
                if ut:
                    date = ut
            done += 1
            if done % 500 == 0:
                log(f"    进度 {done}/{len(ids)}  已得 {len(metrics)}")
    json.dump({"date": date, "done": sorted(metrics.keys()), "metrics": metrics},
              open(os.path.join(ACCT_DIR, "overview_1d.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bj = (datetime.datetime.fromtimestamp(int(date), datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y-%m-%d") if date else ""
    rows = []
    for tid in ids:
        mm = metrics.get(tid)
        if not mm:
            continue
        nm, ar = libmap.get(tid, ("", ""))
        rows.append([tid, nm, ar, mm.get("2"), mm.get("1"), mm.get("3"), bj])
    for path in [os.path.join(ACCT_DIR, "汽水昨日数据.csv"),
                 os.path.join(ACCT_DIR, f"汽水昨日数据_{bj}.csv") if bj else None]:
        if not path:
            continue
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["track_id", "歌名", "作者", "昨日汽水播放量", "昨日汽水热度指数", "昨日付费播放指数", "数据日期"])
            for tid, nm, ar, pl, ht, py, d in rows:
                w.writerow([tid, nm, ar, pl if pl is not None else "", ht if ht is not None else "", py if py is not None else "", d])
    log(f"    完成：{len(metrics)} 首 | 数据日期(北京)={bj}")
    return bj


def refresh_settlement(cookies):
    log("\n[3/5] 刷新结算明细 ...")
    # 1) 发现月份区间
    # 注意：接口把 startPeriod/endPeriod 放在【顶层】(无 data 包裹)，
    # 个别历史/灰度版本可能包在 data 里 —— 两种都兼容。
    months = []
    try:
        pr = py_get(f"{SETTLE_API}/period_range", cookies)
        _d = pr if isinstance(pr, dict) else {}
        sp = _d.get("startPeriod") or (_d.get("data") or {}).get("startPeriod")
        ep = _d.get("endPeriod") or (_d.get("data") or {}).get("endPeriod")
        if sp and ep:
            y0, m0 = int(str(sp)[:4]), int(str(sp)[4:6])
            y1, m1 = int(str(ep)[:4]), int(str(ep)[4:6])
            cur = (y0, m0)
            while (cur[0], cur[1]) <= (y1, m1):
                months.append(f"{cur[0]}{cur[1]:02d}")
                cur = (cur[0], cur[1] + 1) if cur[1] < 12 else (cur[0] + 1, 1)
    except Exception as e:
        log(f"    period_range 失败: {e}")
    if not months:
        months = sorted(f[5:-4] for f in os.listdir(DETAIL_DIR)
                        if f.startswith("结算明细_") and f.endswith(".csv"))
    if not months:
        # 显式告警：当前账号查不到任何已结算单，不要静默生成空表
        log("    ⚠️ 未发现任何已结算月份（period_range 为空，且本地也无结算明细缓存）。")
        log("       → 收益三表（月度汇总 / 逐歌明细 / 逐歌累计）将为空。")
        log("       常见原因（按可能性排序）：")
        log("         1) 当前登录的不是产生收益的【那个创作者账号】（换号了）；")
        log("         2) 该账号确实还没有出过结算单；")
        log("         3) 登录态失效（Cookie 过期，请在 Edge 重新登录后台）。")
        log("       处理建议：确认登录正确账号后重跑本程序；")
        log("       如需先看历史付费数据，可用已归档的 accounts/_legacy 临时重建看板。")
    else:
        log(f"    待下载月份: {months}")
    for p in months:
        ok = False
        for attempt in range(3):
            try:
                j = py_get(f"{SETTLE_API}/download?time={p}", cookies)
                durl = j.get("downloadUrl")
                if durl:
                    txt = py_get(durl, cookies, is_json=False, timeout=60)
                    open(os.path.join(DETAIL_DIR, f"结算明细_{p}.csv"), "w", encoding="utf-8").write(txt)
                    log(f"    OK {p} 行数={len(txt.splitlines())}")
                    ok = True
                    break
            except Exception as e:
                log(f"    {p} 重试 {attempt+1}: {e}")
                time.sleep(2)
        if not ok:
            log(f"    !! 下载失败 {p}")
    return months


# ---------------- 重建收益三表 ----------------
def rebuild_revenue():
    log("\n[4/5] 重建收益三表 ...")
    month_files = sorted([f for f in os.listdir(DETAIL_DIR) if f.startswith("结算明细_") and f.endswith(".csv")])
    months = [f[5:-4] for f in month_files]
    log(f"    月份: {months}")
    lib = json.load(open(os.path.join(ACCT_DIR, "曲库索引.json"), encoding="utf-8"))
    lib_ids = {it["track_id"] for it in lib}

    cols = ["月份", "结算单日期", "收入日期", "歌曲id", "歌曲名称", "歌手名称", "平台", "收入类型", "权利比例",
            "免费播放量", "付费播放量", "下载量", "订购量", "广告收入", "付费收入", "分成收入", "对齐曲库"]
    long_rows, agg, month_settle_date = [], {}, {}
    for cy in months:
        with open(os.path.join(DETAIL_DIR, f"结算明细_{cy}.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sid, name, artist = r["歌曲id"], r["歌曲名称"], r["歌手名称"]
                try:
                    amt = float(r["分成收入"])
                except Exception:
                    amt = 0.0
                long_rows.append([cy, r.get("结算单日期", ""), r.get("收入日期", ""), sid, name, artist,
                                  r["平台"], r.get("收入类型", ""), r.get("权利比例", ""),
                                  r.get("免费播放量", ""), r.get("付费播放量", ""), r.get("下载量", ""),
                                  r.get("订购量", ""), r.get("广告收入", ""), r.get("付费收入", ""),
                                  r["分成收入"], "是" if sid in lib_ids else "否"])
                if cy not in month_settle_date and r.get("结算单日期"):
                    month_settle_date[cy] = r["结算单日期"]
                if sid not in agg:
                    agg[sid] = {"name": name, "artist": artist, "pm": {}, "total": 0.0}
                agg[sid]["pm"][cy] = agg[sid]["pm"].get(cy, 0.0) + amt
                agg[sid]["total"] += amt

    with open(os.path.join(ACCT_DIR, "收益逐歌明细_全量.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for row in long_rows:
            w.writerow(row)

    with open(os.path.join(ACCT_DIR, "收益逐歌累计.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["歌曲id", "歌曲名称", "演唱者", "累计分成收入(元)", "有收益月份数",
                    "各月(元: " + ",".join(months) + ")"])
        for sid, a in sorted(agg.items(), key=lambda kv: kv[1]["total"], reverse=True):
            pm = a["pm"]
            detail = ",".join(f"{m}:{pm.get(m, 0):.2f}" for m in months)
            w.writerow([sid, a["name"], a["artist"], f"{a['total']:.2f}", len(pm), detail])

    # 月度汇总：沿用旧表的官方金额/单号/日期（更准），新月份用明细求和
    old_map = {}
    old_path = os.path.join(ACCT_DIR, "收益月度汇总.csv")
    if os.path.exists(old_path):
        with open(old_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r["结算周期(年月)"].isdigit() and len(r["结算周期(年月)"]) == 6:
                    old_map[r["结算周期(年月)"]] = r
    tot = 0.0
    with open(old_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["结算周期(年月)", "结算单号", "结算金额(元)", "结算状态", "结算日期"])
        for cy in months:
            old = old_map.get(cy)
            if old and old.get("结算金额(元)"):
                amt = float(old["结算金额(元)"]); order = old.get("结算单号", ""); status = old.get("结算状态", "结算成功")
                sdate = old.get("结算日期", "")
            else:
                amt = sum(a["pm"].get(cy, 0.0) for a in agg.values()); order = ""; status = "结算成功"
                sdate = month_settle_date.get(cy, "")
            w.writerow([cy, order, f"{amt:.2f}", status, sdate])
            tot += amt
        w.writerow(["合计", "", f"{tot:.2f}", "", ""])
    log(f"    月度汇总: {len(months)} 月 合计 {tot:.2f} 元")
    log(f"    逐歌明细: {len(long_rows)} 行 | 逐歌累计: {len(agg)} 首")


def _revenue_is_empty():
    """判断当前账号收益三表是否为空（未抓到结算单）。"""
    try:
        p = os.path.join(ACCT_DIR, "收益月度汇总.csv")
        if not os.path.exists(p):
            return True
        rows = list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))
        return not any(r.get("结算周期(年月)", "").strip().isdigit() for r in rows)
    except Exception:
        return True


def run_update(reinit=False):
    """完整流水线（CLI 与 GUI 共用）。返回结果 dict；进度走模块级 log()。"""
    cookies, ckm = get_cookies()
    if not cookies:
        log("\n[错误] 未检测到 CDP / Cookie（浏览器未开、或未登录创作者后台）。")
        log("  请先点【登录账号】拉起专用浏览器，在其中登录 music.douyin.com 后再更新。")
        log(cdp_manual_hint())
        return {"ok": False, "error": "no_cookie"}
    log(f"已取得 Cookie（长度 {len(cookies)}），开始直连接口 ...")

    # ---- 账号隔离：按 uid 决定数据目录，首次运行时迁移根目录遗留数据 ----
    uid = get_account_uid(ckm) or ""
    global ACCT_DIR, DETAIL_DIR
    if uid:
        acctpath.set_current_uid(uid)
        moved = acctpath.migrate_root_to(uid)
        ACCT_DIR = acctpath.account_dir(uid)
        if moved:
            log(f"    已为账号 {uid} 整理历史数据（accounts/{uid}/ 或归档 _legacy）")
    else:
        log("    [提示] Cookie 中未取到 uid，数据暂存根目录（建议确认已登录正确账号）。")
    DETAIL_DIR = os.path.join(ACCT_DIR, "结算明细")
    os.makedirs(DETAIL_DIR, exist_ok=True)
    log(f"    数据目录：{ACCT_DIR}")

    reasons = need_bootstrap(ckm)
    if reinit:
        reasons = reasons or ["手动 --reinit"]
    if reasons:
        log("  触发引导原因：" + "；".join(reasons))
        n = bootstrap_catalog(cookies, ckm)
        if not n:
            log("\n[错误] 引导失败，未生成歌单，已中止。请确认 Edge 中已登录正确的创作者账号。")
            return {"ok": False, "error": "bootstrap_failed"}

    refresh_yesterday(cookies)
    refresh_settlement(cookies)
    rebuild_revenue()

    # 收益为空时显式标记（换号/无结算单），GUI 与结果会提示，而不是静默空表
    rev_empty = _revenue_is_empty()
    if rev_empty:
        log("\n    ⚠️ 收益数据为空：当前账号未抓到任何结算收益。")
        log("       （付费/收益明细已置空；如需查看历史付费数据，见上方建议或 accounts/_legacy）")

    log("\n[5/5] 重建看板 ...")
    try:
        import io, contextlib, importlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            import build_dashboard
            importlib.reload(build_dashboard)
        for line in buf.getvalue().splitlines():
            if line.strip():
                log("    " + line.strip())
        log("    看板已重建: 汽水数据看板.html")
    except Exception as e:
        log(f"    !! 看板重建失败: {e}")

    log("\n完成。看板已刷新。")
    return {"ok": True, "revenue_empty": rev_empty,
            "revenue_hint": ("当前账号未抓到结算收益（换号或无结算单）；历史付费数据在 accounts/_legacy"
                             if rev_empty else "")}


def main():
    if "--login" in sys.argv:
        log("=" * 60)
        log("汽水音乐数据 · 登录账号", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        log("=" * 60)
        if login_account():
            log("已在专用浏览器打开登录页，请扫码/登录；登录完成后运行本程序（或点【重抓歌单】）。")
        else:
            log(cdp_manual_hint())
        return True
    if "--logout" in sys.argv:
        log("=" * 60)
        log("汽水音乐数据 · 退出账号", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        log("=" * 60)
        ok, n = logout_account()
        log(f"已清除汽水/抖音相关 Cookie {n} 条并重置本地账号记录。" if ok else "未能连接浏览器，仅重置了本地账号记录；请手动在浏览器退出登录。")
        return True
    log("=" * 60)
    log("汽水音乐数据 · 一键更新  ", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    log("=" * 60)
    run_update(reinit="--reinit" in sys.argv)
    return True


def _msgbox(text, title="汽水数据更新"):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    except Exception:
        pass


if __name__ == "__main__":
    ok = False
    try:
        ok = main()
    except Exception as e:
        print("运行异常:", e)
    if getattr(sys, "frozen", False):
        _msgbox("数据更新完成，可双击 汽水数据看板.html 查看最新数据。"
                if ok else "数据更新出现问题，请以管理员身份查看上方日志或重新运行。")
