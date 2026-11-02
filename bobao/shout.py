"""The 喊话 page: friends on your Wi-Fi scan a QR code, type a line, and this Mac says it.
Your own lines (bobao clip) are buttons on it too.

    bobao shout on [--voice 安然 --budget 2]   turn it on, print the link, show the QR code
    bobao shout off | link

It listens on your local network at /s/<token>; without the token there is nothing there.
Typed lines are read by the Mac's voice, free and instant. With --voice and --budget, they
are read in that RooYun voice instead, a few seconds later, until the day's budget (credits)
is spent; then the Mac's voice again. One line per 3 seconds, 60 characters at most.
"""

import hmac
import json
import os
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, paths, share
from .log import log

SPEND = os.path.join(paths.HOME, "shout-spend.json")   # {date: credits spent by guests}
MAX_CHARS, GAP = 60, 3


def links(port, token):
    host = socket.gethostname().split(".")[0]
    try:
        r = subprocess.run(["/usr/sbin/scutil", "--get", "LocalHostName"], capture_output=True, text=True)
        host = r.stdout.strip() or host
    except Exception:
        pass
    out = [f"http://{host}.local:{port}/s/{token}"]   # the address can change; the name works on iPhones
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))   # no packet is sent; this only picks the Wi-Fi address
        out.insert(0, f"http://{s.getsockname()[0]}:{port}/s/{token}")   # any phone can open this one
        s.close()
    except OSError:
        pass
    return out


def spent_today():
    return (config.read_json(SPEND, {}) or {}).get(time.strftime("%Y-%m-%d"), 0)


def add_spent(credits):
    d = config.read_json(SPEND, {}) or {}
    today = time.strftime("%Y-%m-%d")
    with open(SPEND, "w") as f:
        json.dump({today: round(d.get(today, 0) + credits, 4)}, f)


def say_rooyun(cfg, text, speaker):
    """Reads `text` in the shout voice if today's budget allows; returns False to fall back."""
    from . import rooyun
    sh = cfg["sources"]["shout"]
    if not sh.get("voice") or not sh.get("budget"):
        return False
    try:
        client = rooyun.Client(cfg["rooyun"]["base"])
        model, params = share.job(client, cfg, {"voice": sh["voice"]}, text)
        price, available = share.quote(client, model, params)
        if spent_today() + price > sh["budget"] or price > available:
            return False
        mp3 = os.path.join(tempfile.mkdtemp(prefix="bobao-shout-"), "a.mp3")
        share.generate(client, model, params, str(uuid.uuid4()), mp3)
        add_spent(price)
        speaker.put({"sound": "doorbell", "file": mp3, "text": text, "segments": []}, cfg)
        return True
    except BaseException as e:   # SystemExit included: a failed line is read by the Mac instead
        log(f"喊话用 RooYun 生成失败，改用电脑声音：{e}")
        return False


def mac_utterance(text):
    return {"sound": "doorbell", "text": text, "segments": [({}, text)]}


def serve(get_cfg, speaker):
    state = {"last": 0}
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, kind="application/json; charset=utf-8"):
            body = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", kind)
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def route(self):
            """(cfg, rest of the path) when the token is right and the page is on, else None."""
            cfg = get_cfg()
            sh = cfg["sources"]["shout"]
            parts = self.path.split("?")[0].strip("/").split("/")
            if not sh.get("enabled") or not sh.get("token") or len(parts) < 2 or parts[0] != "s" \
                    or not hmac.compare_digest(parts[1], sh["token"]):
                self.send(404, b"not here", "text/plain")
                return None
            return cfg, "/".join(parts[2:])

        def do_GET(self):
            r = self.route()
            if not r:
                return
            cfg, rest = r
            if rest == "":
                return self.send(200, page(cfg).encode(), "text/html; charset=utf-8")
            if rest == "clips":
                return self.send(200, [{"name": c["name"], "text": c["text"], "voice": c.get("voiceName", "")}
                                       for c in share.load() if c.get("file")])
            self.send(404, {"ok": False})

        def do_POST(self):
            r = self.route()
            if not r:
                return
            cfg, rest = r
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("content-length") or 0), 4096)) or b"{}")
            except ValueError:
                return self.send(400, {"ok": False, "error": "看不懂"})
            with lock:
                wait = GAP - (time.time() - state["last"])
                if wait > 0:
                    return self.send(429, {"ok": False, "error": f"慢一点，{int(wait) + 1} 秒后再喊"})
                if speaker.q.qsize() > 3:
                    return self.send(429, {"ok": False, "error": "前面还在念，稍等一下"})
                state["last"] = time.time()
            if rest == "play":
                c = share.find(str(body.get("name") or ""))
                if not c or not c.get("file") or not os.path.exists(c["file"]):
                    return self.send(404, {"ok": False, "error": "没有这一句"})
                log(f"喊话页播放：{c['name']}")
                speaker.put({"sound": None, "file": c["file"], "text": c["text"], "segments": []}, cfg)
                return self.send(200, {"ok": True})
            if rest == "say":
                text = " ".join(str(body.get("text") or "").split())[:MAX_CHARS]
                if not text:
                    return self.send(400, {"ok": False, "error": "写点什么吧"})
                log(f"喊话：{text}")
                sh = cfg["sources"]["shout"]
                if sh.get("voice") and sh.get("budget"):
                    def run():
                        if not say_rooyun(cfg, text, speaker):
                            speaker.put(mac_utterance(text), dict(cfg, engine="mac"))
                    threading.Thread(target=run, daemon=True).start()
                    return self.send(200, {"ok": True, "note": "正在用好听的声音生成，几秒后就念"})
                speaker.put(mac_utterance(text), dict(cfg, engine="mac"))
                return self.send(200, {"ok": True})
            self.send(404, {"ok": False})

    port = int(get_cfg()["sources"]["shout"].get("port", 8769))
    server = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"喊话页已开启，端口 {port}")
    return server


def page(cfg):
    name = cfg.get("称呼") or ""
    return PAGE.replace("__NAME__", json.dumps(name, ensure_ascii=False)).replace("__MAX__", str(MAX_CHARS))


PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Bobao 喊话</title>
<style>
:root{--bg:#fff8f3;--card:#fff;--fg:#2b1d16;--muted:#8a766b;--line:#f0e2d8;--acc:#ff6b4a;--accbg:#ffe9e2}
@media (prefers-color-scheme:dark){:root{--bg:#1a1411;--card:#241c18;--fg:#f6ece6;--muted:#a8958a;--line:#3a2e28;--acc:#ff7d5e;--accbg:#3a2620}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,"PingFang SC",sans-serif}
main{max-width:520px;margin:0 auto;padding:28px 16px 40px}
h1{font-size:26px;margin:0 0 4px}p.sub{color:var(--muted);margin:0 0 22px}
.box{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px}
textarea{width:100%;border:0;background:transparent;color:var(--fg);font:inherit;font-size:18px;resize:none;outline:none;min-height:84px}
.bar{display:flex;align-items:center;gap:10px}.count{color:var(--muted);font-size:13px;margin-right:auto}
button{font:inherit;border:0;border-radius:999px;cursor:pointer}
.go{background:var(--acc);color:#fff;font-weight:600;padding:10px 22px;font-size:17px}
.go:disabled{opacity:.5}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 26px}
.chips button{background:var(--accbg);color:var(--acc);padding:7px 14px;font-size:15px}
h2{font-size:16px;margin:0 0 10px;color:var(--muted);font-weight:600}
.clips{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.clips button{background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:14px;padding:12px;text-align:left}
.clips b{display:block}.clips span{color:var(--muted);font-size:13px}
#msg{min-height:24px;margin-top:12px;color:var(--acc);font-weight:600;text-align:center}
footer{margin-top:32px;color:var(--muted);font-size:13px;text-align:center}footer a{color:inherit}
</style></head><body><main>
<h1>📣 喊一句</h1>
<p class="sub">写下想说的话，这台电脑马上大声念出来。</p>
<div class="box"><textarea id="t" maxlength="__MAX__" placeholder="比如：欢迎来玩，饮料在冰箱里自己拿"></textarea>
<div class="bar"><span class="count" id="c">0/__MAX__</span><button class="go" id="go">喊出来</button></div></div>
<div id="msg"></div>
<div class="chips" id="chips"></div>
<section id="board" hidden><h2>主人准备好的</h2><div class="clips" id="clips"></div></section>
<footer>由 <a href="https://funengzhe.github.io/bobao/">Bobao 定制播报</a> 提供</footer>
</main><script>
const base = location.pathname.replace(/\\/$/, ""), name = __NAME__;
const $ = id => document.getElementById(id);
const ideas = ["开饭啦，大家快来吃", "欢迎光临，随便坐", "生日快乐！", (name || "主人") + "，有人找你", "谁赢了谁请客", "五分钟后出发"];
ideas.forEach(s => { const b = document.createElement("button"); b.textContent = s; b.onclick = () => { $("t").value = s; count(); }; $("chips").append(b); });
function count() { $("c").textContent = $("t").value.length + "/__MAX__"; }
$("t").oninput = count;
function note(s) { $("msg").textContent = s; clearTimeout(note.t); note.t = setTimeout(() => $("msg").textContent = "", 3500); }
async function post(path, body) {
  try {
    const r = await fetch(base + path, {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
    const d = await r.json(); note(d.ok ? (d.note || "念出来啦 🔊") : d.error);
    return d.ok;
  } catch (e) { note("连不上，确认手机和电脑在同一个 Wi-Fi"); }
}
$("go").onclick = async () => { const s = $("t").value.trim(); if (!s) return note("写点什么吧");
  $("go").disabled = true; if (await post("/say", {text: s})) { $("t").value = ""; count(); } setTimeout(() => $("go").disabled = false, 3000); };
fetch(base + "/clips").then(r => r.json()).then(list => { if (!list.length) return; $("board").hidden = false;
  list.forEach(c => { const b = document.createElement("button"); b.innerHTML = "<b></b><span></span>";
    b.querySelector("b").textContent = c.text; b.querySelector("span").textContent = c.voice ? "🔊 " + c.voice : "🔊";
    b.onclick = () => post("/play", {name: c.name}); $("clips").append(b); }); });
</script></body></html>"""


def qr_page(urls):
    """A page on this Mac with the QR code, for guests to scan."""
    path = os.path.join(paths.HOME, "shout-qr.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(QR.replace("__URL__", urls[0]).replace("__URLS__", "<br>".join(urls)))
    return path


QR = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>扫码喊话</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#fff8f3;color:#2b1d16;font:18px/1.6 -apple-system,"PingFang SC",sans-serif;text-align:center}
body>div{padding:16px;max-width:100%}#q{background:#fff;padding:22px;border-radius:24px;display:inline-block;box-shadow:0 10px 40px #ff6b4a22;max-width:100%}
#q img,#q canvas{max-width:100%;height:auto}h1{font-size:clamp(24px,5vw,40px);margin:0 0 6px}p{color:#8a766b;margin:6px 0;word-break:break-all}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script></head>
<body><div><h1>📣 扫码，让这台电脑替你喊一句</h1><p>手机连上同一个 Wi-Fi，用相机扫一扫</p><div id="q"></div><p style="font-size:14px">__URLS__</p></div>
<script>new QRCode(document.getElementById("q"), {text: "__URL__", width: 320, height: 320});</script></body></html>"""


def turn_on(voice=None, budget=None):
    user = config.read_json(paths.CONFIG, {}) or {}
    sh = user.setdefault("sources", {}).setdefault("shout", {})
    sh["enabled"] = True
    sh["token"] = sh.get("token") or secrets.token_urlsafe(6)
    if voice is not None:
        sh["voice"] = voice
    if budget is not None:
        sh["budget"] = budget
    config.save_user(user)
    return config.load()["sources"]["shout"]


def turn_off():
    user = config.read_json(paths.CONFIG, {}) or {}
    user.setdefault("sources", {}).setdefault("shout", {})["enabled"] = False
    config.save_user(user)
