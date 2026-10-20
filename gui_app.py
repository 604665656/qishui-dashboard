# -*- coding: utf-8 -*-
"""
汽水音乐数据 · 可视化桌面程序（单文件 EXE 入口）
==============================================
用「本地 HTTP 服务 + 系统 Edge 应用模式窗口」展示数据看板与可视化工具条：
  - 顶栏状态：账号(uid脱敏) / 歌单数 / 数据日期 / 累计收益 / 上次更新 / 更新中标记
  - 按钮：一键更新数据 / 重抓歌单(换账号) / 刷新显示 / 浏览器打开 / 日志
  - 看板在 <iframe> 中由系统 Edge 渲染（零联网，数据由本机服务供应）。

原理：本程序启动本地服务(127.0.0.1)，再用 Edge 的 --app 模式打开一个无地址栏的窗口加载本服务页面；
      页面上的按钮通过 fetch 调用本服务接口触发更新，并轮询日志/状态实时显示。
      关掉该窗口后，程序自动退出（心跳超时）。

前置：本机已用 CDP 启动并登录的 Edge（默认端口 9222，user-data-dir=C:\\edge-cdp）。
"""
import os, sys, json, datetime, threading, atexit, time, http.server, socketserver, subprocess, webbrowser
from urllib.parse import quote, urlparse, parse_qs
import update_all as UA
import acctpath  # 账号隔离：读当前账号数据目录

BASE = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(BASE, "汽水数据看板.html")
GUI_LOG = os.path.join(BASE, "gui.log")

_PORT = 8731
_LOGS = []
LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_RUNNING = False
_LAST_PING = time.time()


def glog(*a):
    s = " ".join(str(x) for x in a)
    try:
        with open(GUI_LOG, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def push_log(s):
    print(s, flush=True)
    with LOCK:
        _LOGS.append(s)


def _read_status():
    info = {"uid": "", "song_count": 0, "data_date": "", "total_revenue": None,
            "last_update": "", "running": _RUNNING}
    ad = acctpath.active_account_dir()
    try:
        ap = os.path.join(ad, "account.json")
        if os.path.exists(ap):
            acc = json.load(open(ap, encoding="utf-8"))
            uid = acc.get("uid", "") or ""
            if len(uid) > 10:
                uid = uid[:6] + "****" + uid[-4:]
            info["uid"] = uid
    except Exception:
        pass
    try:
        lp = os.path.join(ad, "曲库索引.json")
        if os.path.exists(lp):
            info["song_count"] = len(json.load(open(lp, encoding="utf-8")))
    except Exception:
        pass
    try:
        import csv
        p = os.path.join(ad, "汽水昨日数据.csv")
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            if len(rows) > 1:
                info["data_date"] = rows[-1][-1] if rows[-1] else (rows[1][-1] if len(rows) > 1 else "")
    except Exception:
        pass
    try:
        import csv
        p = os.path.join(ad, "收益月度汇总.csv")
        if os.path.exists(p):
            tot = 0.0
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("结算周期(年月)", "").isdigit():
                        try:
                            tot += float(r.get("结算金额(元)", 0) or 0)
                        except Exception:
                            pass
            info["total_revenue"] = tot
    except Exception:
        pass
    try:
        if os.path.exists(DASH):
            info["last_update"] = datetime.datetime.fromtimestamp(os.path.getmtime(DASH)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    info["running"] = _RUNNING
    return info


def _wrapper_html():
    dash_path = quote("汽水数据看板.html")
    mtime = int(os.path.getmtime(DASH)) if os.path.exists(DASH) else 0
    init_src = ("/%s?v=%d" % (dash_path, mtime)) if os.path.exists(DASH) else "/__welcome__"
    return """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>
 html,body{margin:0;height:100%;font-family:"Microsoft YaHei",sans-serif;overflow:hidden;background:#0b1220}
 #bar{position:fixed;top:0;left:0;right:0;height:56px;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:space-between;padding:0 14px;box-sizing:border-box;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.35)}
 #bar b{color:#38bdf8;font-size:15px}
 .qs-status{font-size:12px;color:#94a3b8;margin-left:10px}
 #bar button{margin-left:8px;padding:6px 12px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer;font-size:13px}
 #bar button:hover{background:#1d4ed8}
 #frame{position:absolute;top:56px;left:0;right:0;bottom:0;width:100%;height:calc(100% - 56px);border:0;background:#fff}
 #log{position:fixed;bottom:0;left:0;right:0;max-height:32%;overflow:auto;background:rgba(15,23,42,.96);color:#a5f3fc;font:12px/1.5 Consolas,monospace;padding:8px 12px;z-index:20;display:none}
 .running{color:#fbbf24}
</style></head>
<body>
 <div id="bar">  <div><b>汽水音乐数据看板</b><span class="qs-status" id="status">加载中…</span></div>
  <div><button id="btn-login" style="background:#0ea5e9">登录账号</button><button id="btn-logout" style="background:#475569">退出账号</button><button id="btn-update">一键更新数据</button><button id="btn-reinit">重抓歌单(换账号)</button>
  <button id="btn-refresh">刷新显示</button><button id="btn-open">浏览器打开</button><button id="btn-log">日志</button></div></div>
 <iframe id="frame" src="__INIT_SRC__"></iframe>
 <div id="log"></div>
 <script>
  var DASH_PATH="__DASH_PATH__";
  var since=0, prevUpdate="";
  function appendLog(s){var p=document.getElementById('log');var d=document.createElement('div');d.textContent=s;p.appendChild(d);p.scrollTop=p.scrollHeight;}
  function goDash(){var f=document.getElementById('frame');if(f)f.src='/'+DASH_PATH+'?t='+Date.now();}
  function pollLogs(){fetch('/__api/logs?since='+since).then(function(r){return r.json();}).then(function(d){d.lines.forEach(appendLog);since=d.total;}).catch(function(){});}
  function pollStatus(){fetch('/__api/status').then(function(r){return r.json();}).then(function(o){
    var s=document.getElementById('status');
    s.textContent='账号 '+(o.uid||'未登录')+' ｜ 歌单 '+(o.song_count||0)+' 首 ｜ 数据日期 '+(o.data_date||'-')+' ｜ 累计收益 '+((o.total_revenue!=null)?o.total_revenue.toFixed(2):'-')+' 元 ｜ 更新于 '+(o.last_update||'-')+(o.running?' ｜ <span class="running">更新中…</span>':'');
    if(o.last_update && o.last_update!==prevUpdate){prevUpdate=o.last_update;if(o.last_update)goDash();}
  }).catch(function(){});}
  document.getElementById('btn-update').onclick=function(){fetch('/__api/update');};
  document.getElementById('btn-reinit').onclick=function(){if(confirm('将重新抓取当前登录账号歌单并覆盖本地清单，确定？'))fetch('/__api/reinit');};
  document.getElementById('btn-login').onclick=function(){fetch('/__api/login');};
  document.getElementById('btn-logout').onclick=function(){if(confirm('确定退出当前账号？将清除本工具专用浏览器中的汽水/抖音登录态。'))fetch('/__api/logout');};
  document.getElementById('btn-refresh').onclick=function(){goDash();};
  document.getElementById('btn-open').onclick=function(){fetch('/__api/open');};
  document.getElementById('btn-log').onclick=function(){var p=document.getElementById('log');p.style.display=(p.style.display==='none')?'block':'none';};
  setInterval(pollLogs,1000); setInterval(pollStatus,3000); setInterval(function(){fetch('/__api/ping');},2000);
  pollLogs(); pollStatus();
 </script>
</body></html>""".replace("__INIT_SRC__", init_src).replace("__DASH_PATH__", dash_path)


_WELCOME = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>body{font-family:"Microsoft YaHei",sans-serif;background:#0f172a;color:#cbd5e1;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{text-align:center;padding:40px}.card h1{color:#38bdf8}.card p{color:#94a3b8;line-height:1.8}</style></head>
<body><div class="card"><h1>汽水音乐数据看板</h1>
<p>尚未生成看板数据。<br>点击左上角「一键更新数据」开始抓取（需先在 CDP Edge 登录创作者后台）。</p></div></body></html>"""


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a):
        super().__init__(*a, directory=BASE)

    def _send(self, ctype, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        try:
            if path == "/__gui__":
                self._send("text/html; charset=utf-8", _wrapper_html()); return
            if path == "/__welcome__":
                self._send("text/html; charset=utf-8", _WELCOME); return
            if path == "/__api/status":
                self._send("application/json", json.dumps(_read_status(), ensure_ascii=False)); return
            if path == "/__api/logs":
                n = int(qs.get("since", ["0"])[0])
                with LOCK:
                    lines = _LOGS[n:]; total = len(_LOGS)
                self._send("application/json", json.dumps({"total": total, "lines": lines}, ensure_ascii=False)); return
            if path in ("/__api/update", "/__api/reinit"):
                _trigger_update(path == "/__api/reinit")
                self._send("application/json", json.dumps({"ok": True})); return
            if path == "/__api/login":
                _bg_run("登录账号", _login_flow)
                self._send("application/json", json.dumps({"ok": True})); return
            if path == "/__api/logout":
                _bg_run("退出账号", _logout_flow)
                self._send("application/json", json.dumps({"ok": True})); return
            if path == "/__api/ping":
                global _LAST_PING; _LAST_PING = time.time()
                self._send("application/json", json.dumps({"ok": True})); return
            if path == "/__api/open":
                try:
                    os.startfile(DASH)
                except Exception:
                    pass
                self._send("application/json", json.dumps({"ok": True})); return
            return super().do_GET()
        except Exception as e:
            self._send("application/json", json.dumps({"error": str(e)})); return

    def log_message(self, *a):
        pass


def _start_server():
    global _PORT
    srv = None
    for port in range(8731, 8790):
        try:
            srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), _Handler)
            _PORT = port
            break
        except OSError:
            continue
    if srv is None:
        raise RuntimeError("无法在 127.0.0.1 绑定本地端口")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    atexit.register(srv.shutdown)
    return srv


def _trigger_update(reinit):
    global _RUNNING
    if not _RUN_LOCK.acquire(False):
        push_log("上一次更新仍在进行，请稍候。")
        return
    try:
        _RUNNING = True
        UA.log = push_log
        push_log("=== 开始更新（reinit=%s）===" % reinit)
        res = UA.run_update(reinit=bool(reinit))
        if res and res.get("ok"):
            push_log("=== 更新完成 ===")
        else:
            push_log("=== 更新未成功：%s ===" % (res.get("error") if res else "未知"))
    except Exception as e:
        push_log("更新异常：" + repr(e))
    finally:
        _RUNNING = False
        _RUN_LOCK.release()


def _bg_run(label, fn):
    """在后台线程跑一个带日志的轻量任务（登录/退出），不阻塞 HTTP。"""
    def _w():
        try:
            push_log("=== %s ===" % label)
            fn()
            push_log("=== %s 完成 ===" % label)
        except Exception as e:
            push_log("异常：" + repr(e))
    threading.Thread(target=_w, daemon=True).start()


def _login_flow():
    push_log("正在确认专用浏览器(CDP)是否已启动...")
    if UA.login_account():
        push_log("专用浏览器已就绪，已在其中打开汽水音乐扫码登录页：%s" % UA.LOGIN_URL)
        push_log("请用手机「抖音 / 汽水音乐」App 扫一扫页面二维码，在手机端点击「确认登录」。")
        push_log("登录完成后点【重抓歌单(换账号)】以重建当前账号歌单与数据。")
    else:
        push_log("未能启动专用浏览器，请手动运行：")
        push_log('  "%s" --remote-debugging-port=%d --user-data-dir=%s'
                 % (UA.MS_EDGE_CANDIDATES[0], UA.PORT, UA.CDP_USER_DATA))


def _logout_flow():
    push_log("正在连接专用浏览器以清除登录态...")
    ok, n = UA.logout_account()
    if ok:
        push_log("已清除汽水/抖音相关 Cookie %d 条，并重置本地账号记录。" % n)
        push_log("当前已退出登录。如需换号：点【登录账号】后用新账号登录，再点【重抓歌单】。")
    else:
        push_log("未能连接专用浏览器，仅重置了本地账号记录；请手动在浏览器退出登录。")


def _watchdog():
    while True:
        time.sleep(5)
        if time.time() - _LAST_PING > 25:
            glog("心跳超时，退出")
            os._exit(0)


def _launch_edge(url):
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                subprocess.Popen([c, "--app=%s" % url, "--window-size=1280,860"])
                return True
            except Exception as e:
                glog("launch edge err", e)
    try:
        webbrowser.open(url)
        return False
    except Exception:
        return False


def main():
    glog("=== gui start %s ===" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    _start_server()
    threading.Thread(target=_watchdog, daemon=True).start()
    url = "http://127.0.0.1:%d/__gui__" % _PORT
    ok = _launch_edge(url)
    glog("launched edge=%s url=%s" % (ok, url))
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        glog("FATAL", repr(e))
        print("启动失败:", e)
