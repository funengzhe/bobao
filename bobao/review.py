"""The listening page: every way each notification type can sound, sound effect first,
in the voices as recorded. Under each sentence are the recorded pieces it is stitched
from; tap the ones you don't like and press 重录, then run `bobao voice record`.

    bobao review       opens http://127.0.0.1:8767
"""

import html
import json
import os
import random
import shutil
import tempfile
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import clips, compose, config, paths, speaker
from .config import voice_key
from .events import TYPES, Event, Match
from .log import log


def sample_event(cfg, kind, platform):
    f = {}
    if kind == "收款":
        f = {"金额": "$19.90", "方式": (cfg["values"].get("方式") or [""])[0], "备注": "首次充值"}
    elif kind == "套餐":
        f = {"金额": "¥99", "套餐": (cfg["values"].get("套餐") or [""])[0]}
    return Event("webhook", "", f"示例 {kind}", fields=f, platform=platform)


def samples(cfg):
    """[(group, utterance)] covering every template, rule and follow-up line once."""
    out, seen = [], set()
    rnd = random.Random(3)
    quiet = dict(cfg, tease=dict(cfg["tease"], chance=0))
    for kind in TYPES:
        t = compose.type_settings(cfg, kind)
        if t.get("enabled") is False or not t.get("say"):
            continue
        for platforms, name, own in compose.contexts(cfg, kind):
            for p in platforms[:1] if not name else platforms:
                for template in own or (t["say"] if isinstance(t["say"], list) else [t["say"]]):
                    m = Match(kind, p, name, {"say": template}, 0)
                    utt = compose.render(m, sample_event(cfg, kind, p), quiet, rnd)
                    if utt and utt["text"] not in seen:
                        seen.add(utt["text"])
                        out.append((kind, utt))
        lines = cfg["tease"].get("lines", {})
        if t.get("tease", True) and cfg["tease"].get("chance"):
            base = next((u for k, u in out if k == kind), None)
            for k, ls in lines.items():
                if k.split("·")[0] == kind or (kind == "收款" and k.startswith("大单")):
                    for line in ls:
                        line = compose.fill(line, {"称呼": cfg["称呼"], "平台": compose.spoken_platform(cfg, next(iter(cfg["platforms"]), ""))})
                        if base and line not in seen:
                            seen.add(line)
                            out.append((f"{kind} · 接话（约 {int(cfg['tease']['chance'] * 100)}% 会接）",
                                        dict(base, segments=base["segments"][:1] + [(config.voice_for(cfg, "接话"), line)],
                                             text=base["text"] + "｜" + line)))
    for key, kind in (("say", "告警"), ("back", "恢复")):
        for line in cfg["health"].get(key, []):
            out.append(("播报自己断了 / 恢复", {"sound": cfg["sounds"].get(kind), "text": compose.fill(line, cfg),
                                         "segments": [(config.voice_for(cfg, kind), compose.fill(line, cfg))]}))
    return out


def pieces(utt, index):
    """[(voice key, phrase)] a recorded utterance is stitched from."""
    out = []
    for voice, text in utt["segments"]:
        vkey = voice_key(voice)
        files = {os.path.join(paths.CLIPS, f): k for k, f in index.get(vkey, {}).items()}
        found = clips.find(text, {k: os.path.join(paths.CLIPS, f) for k, f in index.get(vkey, {}).items()}) or []
        out += [(vkey, files[f]) for part in found for f, *_ in part]
    return out


def build(cfg, folder):
    index = clips.load()
    items = []
    for n, (group, utt) in enumerate(samples(cfg)):
        voice = os.path.join(folder, f"v{n}.wav")
        recorded = cfg["engine"] == "rooyun" and speaker.render_wav(utt, cfg, voice)
        item = {"group": group, "text": utt["text"].replace("｜", " ｜ "), "recorded": bool(recorded),
                "pieces": pieces(utt, index) if recorded else []}
        if recorded:
            out = os.path.join(folder, f"p{n}.wav")
            join([speaker.sound_path(utt.get("sound")), voice], out)
            item["file"] = f"p{n}.wav"
        items.append(item)
    return items


def join(files, out):
    """Sound effect + voice in one WAV, converting the effect to the voice's format."""
    files = [f for f in files if f]
    with tempfile.TemporaryDirectory() as tmp:
        conv = []
        for i, f in enumerate(files):
            c = os.path.join(tmp, f"{i}.wav")
            os.system(f"/usr/bin/afconvert -f WAVE -d LEI16@24000 -c 1 '{f}' '{c}' >/dev/null 2>&1")
            conv.append(c)
        with wave.open(out, "wb") as w:
            for i, c in enumerate(conv):
                with wave.open(c) as r:
                    if i == 0:
                        w.setparams(r.getparams())
                    w.writeframes(b"\0" * int(r.getframerate() * (0.15 if i else 0)) * 2)
                    w.writeframes(r.readframes(r.getnframes()))


def redo(items):
    """Moves the chosen clips out of the library, so the next record run records them again."""
    index, state = clips.load(), config.read_json(paths.RECORDING, {}) or {}
    retired = os.path.join(paths.CLIPS, "retired")
    os.makedirs(retired, exist_ok=True)
    n = 0
    for vkey, phrase in items:
        f = index.get(vkey, {}).pop(phrase, None)
        if f:
            shutil.move(os.path.join(paths.CLIPS, f), os.path.join(retired, f))
            state.pop(f"{vkey}|{phrase}", None)
            n += 1
    clips.save(index)
    with open(paths.RECORDING, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    return n


PAGE = """<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bobao 审听</title><style>
:root{--bg:#fafafa;--fg:#1a1a1a;--mute:#777;--card:#fff;--line:#e5e5e5;--acc:#2a6df4;--warn:#d33}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--mute:#999;--card:#1e1e1e;--line:#333;--acc:#6b9bff;--warn:#f66}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,"PingFang SC",sans-serif}
main{max-width:760px;margin:auto;padding:16px}h1{font-size:20px}h2{font-size:15px;color:var(--mute);margin:24px 0 8px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
audio{width:100%;height:32px;margin-top:6px}.p{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:0 6px;margin:4px 4px 0 0;font-size:12px;cursor:pointer;color:var(--mute)}
.p.on{border-color:var(--warn);color:var(--warn);text-decoration:line-through}.miss{color:var(--warn);font-size:13px}
#bar{position:sticky;bottom:0;background:var(--bg);padding:10px 0;border-top:1px solid var(--line)}button{font:inherit;padding:6px 14px;border-radius:8px;border:0;background:var(--acc);color:#fff}
</style><main><h1>Bobao 审听 · __STYLE__</h1><p style="color:var(--mute)">先放音效，再放播报。点句子下面的小块标出不满意的片段，然后按「重录」，再运行 <code>bobao voice record</code>。</p>
<div id="list"></div><div id="bar"><button id="redo">重录选中的 <span id="n">0</span> 段</button> <span id="msg"></span></div></main>
<script>
const items=__ITEMS__,picked=new Map();let g="";const L=document.getElementById("list");
items.forEach(it=>{if(it.group!==g){g=it.group;const h=document.createElement("h2");h.textContent=g;L.append(h)}
const c=document.createElement("div");c.className="c";const t=document.createElement("div");t.textContent=it.text;c.append(t);
if(it.file){const a=document.createElement("audio");a.controls=true;a.preload="none";a.src="audio/"+it.file;c.append(a)}
else{const m=document.createElement("div");m.className="miss";m.textContent="还没录音（运行 bobao voice record）";c.append(m)}
it.pieces.forEach(([v,p])=>{const s=document.createElement("span");s.className="p";s.textContent=p;s.onclick=()=>{const k=v+"\\u0001"+p;
picked.has(k)?picked.delete(k):picked.set(k,[v,p]);s.classList.toggle("on");document.getElementById("n").textContent=picked.size};c.append(s)});L.append(c)});
document.getElementById("redo").onclick=async()=>{const r=await fetch("redo",{method:"POST",body:JSON.stringify([...picked.values()])});
const d=await r.json();document.getElementById("msg").textContent="已移出 "+d.removed+" 段，运行 bobao voice record 重录"};
</script></html>"""


def serve(port=8767, open_browser=True):
    cfg = config.load()
    folder = tempfile.mkdtemp(prefix="bobao-review-")
    items = build(cfg, folder)
    page = PAGE.replace("__STYLE__", html.escape(cfg["styleName"])).replace("__ITEMS__", json.dumps(items, ensure_ascii=False))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, kind):
            self.send_response(code)
            self.send_header("content-type", kind)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/audio/"):
                name = os.path.basename(self.path)
                p = os.path.join(folder, name)
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return self.send(200, f.read(), "audio/wav")
                return self.send(404, b"", "text/plain")
            self.send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            chosen = json.loads(self.rfile.read(n) or b"[]")
            self.send(200, json.dumps({"removed": redo(chosen)}).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), H)
    recorded = sum(1 for i in items if i["recorded"])
    log(f"审听页面：http://127.0.0.1:{port}  （{len(items)} 句，已录 {recorded} 句）")
    if open_browser:
        os.system(f"/usr/bin/open http://127.0.0.1:{port}")
    server.serve_forever()
