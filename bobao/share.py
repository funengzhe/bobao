"""Lines you make to show off: any sentence, in any RooYun voice, saved as a file you can
send to people, and as a button on the 喊话 page.

    bobao clip make "欢迎来我家玩" [--voice 安然] [--name 欢迎] [--yes]
    bobao clip list | play 名字 | remove 名字

~/.bobao/share/index.json lists them; each is an mp3 there, and a copy (mp3, plus an mp4
with the Bobao card when ffmpeg is installed, for chats that only play videos) goes to the
Desktop. Making one costs RooYun credits: the price is shown first, and requestIds are
kept so a retry never pays twice.
"""

import json
import os
import re
import shutil
import subprocess
import time
import uuid

from . import config, paths, system

DIR = os.path.join(paths.HOME, "share")
INDEX = os.path.join(DIR, "index.json")
CARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "og.png")


def load():
    return config.read_json(INDEX, []) or []


def save(items):
    os.makedirs(DIR, exist_ok=True)
    with open(INDEX + ".tmp", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(INDEX + ".tmp", INDEX)


def find(name):
    return next((c for c in load() if c["name"] == name), None)


def default_name(text):
    return re.sub(r"[^\w一-鿿]+", "", text)[:12] or time.strftime("%H%M%S")


def resolve_voice(name, cfg, catalog):
    """A voice by recommended name or id; none given: the voice in use, or 小柚."""
    if name:
        picked = next((v for v in catalog if name in (v["name"], v["id"])), None)
        return {"voice": picked["id"] if picked else name}, picked["name"] if picked else name
    if cfg["engine"] == "rooyun":
        v = config.voice_for(cfg, "提醒")
        return v, next((c["name"] for c in catalog if c["id"] == v["voice"]), v["voice"])
    return {"voice": catalog[0]["id"]}, catalog[0]["name"]


def job(client, cfg, voice, text):
    meta = {v["voiceId"]: v for v in client.voices()}
    v = dict(voice, kind=meta.get(voice["voice"], {}).get("kind"))
    model, own = client.model_for(v, cfg)
    params = {"text": text, "voiceId": v["voice"]}
    if v.get("emotion") and not own:
        params["emotion"] = v["emotion"]
    return model, params


def quote(client, model, params):
    return client.precheck([{"model": model, "capability": "t2a", "params": {"text": params["text"]}}])


def generate(client, model, params, request_id, dest):
    """Submits (or picks up) one task, waits, downloads the mp3 to dest."""
    task_id = client.generate(request_id, model, params)
    for _ in range(100):
        t = client.task(task_id)
        if t.get("status") in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(3)
    if t.get("status") != "succeeded" or not t.get("assetId"):
        raise SystemExit(f"没生成成功（{t.get('status')}），这一笔没有扣钱，可以再试一次")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    client.download(t["assetId"], dest)


def to_video(mp3, mp4):
    """The Bobao card with the line as sound: chats that won't play an mp3 inline play this."""
    ffmpeg = system.ffmpeg()
    if not ffmpeg or not os.path.exists(CARD):
        return False
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-i", CARD, "-i", mp3, "-shortest",
                        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-vf", "scale=1200:630",
                        "-c:a", "aac", "-b:a", "128k", mp4], capture_output=True)
    return r.returncode == 0


def make(text, voice_name, name, yes, catalog, out=print, ask=input):
    from . import rooyun
    text = text.strip()
    if not text or len(text) > 200:
        raise SystemExit("说一两句就好（200 字以内）")
    cfg = config.load()
    name = name or default_name(text)
    items = load()
    old = next((c for c in items if c["name"] == name), None)
    voice, label = resolve_voice(voice_name, cfg, catalog)
    if old and old.get("file") and old["text"] == text and old.get("voice") == voice["voice"]:
        out(f"「{name}」已经做好了：{old['file']}")
        return old
    client = rooyun.Client(cfg["rooyun"]["base"])
    model, params = job(client, cfg, voice, text)
    price, available = quote(client, model, params)
    out(f"用 {label} 念「{text}」，约 {price} 积分，你的可用积分 {round(available, 2)}")
    if not yes:
        if ask("生成吗？[y/N] ").strip().lower() not in ("y", "yes", "是"):
            out("没有生成")
            return None
    if price > available:
        raise SystemExit("积分不够，请先到 RooYun（如云）充值")
    if not old or old["text"] != text or old.get("voice") != voice["voice"]:
        old = {"name": name, "text": text, "voice": voice["voice"], "voiceName": label, "requestId": str(uuid.uuid4())}
        items = [c for c in items if c["name"] != name] + [old]
        save(items)   # the requestId is kept before submitting, so a retry reuses it
    mp3 = os.path.join(DIR, f"{name}.mp3")
    try:
        generate(client, model, params, old["requestId"], mp3)
    except SystemExit:   # a failed task comes back for the same requestId: the next try needs a new one
        old["requestId"] = str(uuid.uuid4())
        save(items)
        raise
    old.update(file=mp3, made=time.strftime("%Y-%m-%d %H:%M"))
    save(items)
    desk = os.path.expanduser(f"~/Desktop/Bobao-{name}")
    shutil.copy(mp3, desk + ".mp3")
    video = to_video(mp3, desk + ".mp4")
    out(f"做好了：{desk}.mp3" + (f"\n      视频版：{desk}.mp4（发微信、朋友圈、抖音用这个）" if video else
                                   "\n（装了 ffmpeg 的话还会出一个视频版，方便在微信里直接播放）"))
    out("它也会出现在喊话页上，点一下就在这台电脑上播出来（bobao shout on）")
    system.play(mp3)
    return old


def remove(name):
    items = load()
    c = next((x for x in items if x["name"] == name), None)
    if not c:
        raise SystemExit(f"没有叫「{name}」的")
    save([x for x in items if x["name"] != name])
    if c.get("file") and os.path.exists(c["file"]):
        os.remove(c["file"])
