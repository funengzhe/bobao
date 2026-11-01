#!/usr/bin/env python3
"""Builds the listening gallery in docs/: every RooYun voice reading the same passage,
emotions, every style and every scene as it would sound, plus the Mac's free voices.
docs/ is a static page (GitHub Pages or bobao gallery), audio included.

    python3 tools/make_gallery.py              quote what is not recorded yet (free)
    python3 tools/make_gallery.py --record     record it with RooYun (asks first)
    python3 tools/make_gallery.py --mac        Mac voice samples (free, local)
    python3 tools/make_gallery.py --page       rebuild docs/gallery.json only

Recording is idempotent: requestIds live in docs/.gallery-tasks.json (not committed).
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOBAO_HOME", tempfile.mkdtemp(prefix="bobao-gallery-"))

from bobao import compose, config, daemon, rooyun  # noqa: E402
from bobao.events import Event  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
AUDIO = os.path.join(DOCS, "audio")
TASKS = os.path.join(DOCS, ".gallery-tasks.json")
MANIFEST = os.path.join(DOCS, "gallery.json")

PASSAGE = "叮咚，到账 299 元，新客首单。注意，服务器出故障了，请尽快处理。"
PASSAGE_EN = "Cha-ching! You just received 299 dollars from a new customer. Heads up, the server is down, please take a look."
MAC_PASSAGE = PASSAGE
EMOTION_LINE = "老板，服务器出故障了，快去看看。"
EMOTION_VOICES = ["female-shaonv-jingpin", "female-tianmei", "male-qn-jingying-jingpin"]
EMOTIONS = ["happy", "sad", "angry", "fearful", "surprised"]
SAMPLE_CARDS = [("收款", Event("webhook", "", "充值到账", fields={"金额": "¥1299", "方式": "微信", "备注": "首次购买"}, platform="我的店")),
                ("注册", Event("webhook", "", "新用户注册", platform="我的店")),
                ("告警", Event("webhook", "", "服务器宕机", platform="我的店")),
                ("日报", Event("webhook", "", "经营日报", platform="我的店")),
                ("提醒", Event("webhook", "", "收到新反馈", platform="我的店"))]


def slug(*parts):
    import hashlib
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def line_for(cfg, card, seed=4):
    utt, _ = daemon.decide(card, cfg, dry=True, rnd=random.Random(seed))
    return utt


def entries():
    """Every sample: {section, title, sub, text, voice, emotion?} (+ engine mac)."""
    catalog = json.load(open(os.path.join(ROOT, "packs", "voices.json"), encoding="utf-8"))
    out = []
    for v in catalog["voices"]:
        out.append({"section": "音色", "title": v["name"], "sub": f"{v['gender']} · {v['age']} · " + "、".join(v["tags"]),
                    "goodFor": v["goodFor"], "recommended": v["recommended"], "lang": v["lang"], "voiceId": v["id"].strip(),
                    "text": PASSAGE_EN if v["lang"] == "en" else PASSAGE, "voice": v["id"]})
    names = {v["id"]: v["name"] for v in catalog["voices"]}
    for vid in EMOTION_VOICES:
        for e in EMOTIONS:
            out.append({"section": "情绪", "title": f"{names[vid]} · {catalog['emotions'][e]}", "sub": vid, "voiceId": vid,
                        "text": EMOTION_LINE, "voice": vid, "emotion": e})
    for name, p in config.list_packs("styles").items():
        cfg = config.load({"style": name, "platforms": {"我的店": {"say": "我的店"}}, "values": {"方式": ["微信"]}, "bigOrder": {"*": 1000}})
        cfg["tease"]["chance"] = 0
        for kind, card in SAMPLE_CARDS[:3]:
            utt = line_for(cfg, card)
            if utt:
                v = config.voice_for(cfg, kind)
                out.append({"section": "风格", "title": p["name"], "sub": f"{kind} · {names.get(v['voice'], v['voice'])}",
                            "group": name, "description": p.get("description", ""), "voiceId": v["voice"],
                            "text": utt["segments"][0][1], "voice": v["voice"], "emotion": v.get("emotion"), "sound": utt["sound"]})
    for name, p in config.list_packs("scenes").items():
        cfg = config.load({"scene": name, "platforms": {"我的店": {"say": "我的店"}}, "values": {"方式": ["微信"]}})
        cfg["tease"]["chance"] = 0
        for kind, card in sorted(SAMPLE_CARDS, key=lambda kc: kc[0] != p.get("demo")):
            if cfg["types"].get(kind, {}).get("enabled") is False:
                continue
            utt = line_for(cfg, card)
            if utt:
                v = config.voice_for(cfg, kind)
                plays = [k for k in ("收款", "套餐", "注册", "日报", "告警", "恢复", "提醒") if cfg["types"].get(k, {}).get("enabled") is not False]
                out.append({"section": "场景", "title": p["name"], "sub": p["who"], "group": name, "description": p["description"],
                            "plays": plays, "schedule": schedule_text(cfg), "voiceId": v["voice"],
                            "text": utt["segments"][0][1], "voice": v["voice"], "emotion": v.get("emotion"), "sound": utt["sound"]})
                break
    for mv in catalog["mac"]:
        out.append({"section": "Mac 免费声音", "title": mv, "sub": "macOS 自带，不花钱", "voiceId": mv, "text": MAC_PASSAGE,
                    "voice": mv, "engine": "mac"})
    for e in out:
        e["id"] = slug(e.get("engine", "rooyun"), e["voice"], e.get("emotion") or "", e["text"])
        e["file"] = f"audio/{'mac/' if e.get('engine') == 'mac' else ''}{e['id']}.{'m4a' if e.get('engine') == 'mac' else 'mp3'}"
    return out


def schedule_text(cfg):
    s = cfg.get("schedule") or {}
    days = s.get("days")
    parts = []
    if days:
        parts.append("周" + "".join("一二三四五六日"[d - 1] for d in days))
    if s.get("hours"):
        parts.append(s["hours"])
    if s.get("quietHours"):
        parts.append(f"{s['quietHours']} 静音")
    always = [k for k, t in cfg["types"].items() if t.get("always") and t.get("enabled") is not False]
    return ("，".join(parts) or "全天") + (f"（{'、'.join(always)}全天）" if always and parts else "")


def todo(items):
    return [e for e in items if e.get("engine") != "mac" and not os.path.exists(os.path.join(DOCS, e["file"]))]


def jobs(client, items):
    model = client.model_for({"voice": "", "kind": "system"}, config.load({}))[0]   # all gallery voices are RooYun's own
    out = []
    for e in items:
        params = {"text": e["text"], "voiceId": e["voice"]}
        if e.get("emotion"):
            params["emotion"] = e["emotion"]
        out.append((e, model, params))
    return out


def record(client, js):
    state = json.load(open(TASKS)) if os.path.exists(TASKS) else {}

    def save():
        json.dump(state, open(TASKS, "w"), ensure_ascii=False, indent=1)

    os.makedirs(AUDIO, exist_ok=True)
    for n, (e, model, params) in enumerate(js, 1):
        s = state.setdefault(e["id"], {})
        if s.get("taskId"):
            continue
        s.setdefault("requestId", str(uuid.uuid4()))
        save()
        try:
            s["taskId"] = client.generate(s["requestId"], model, params)
        except rooyun.ApiError as err:
            print("  提交失败", e["title"], err)
            continue
        save()
        print(f"  已提交 {n}/{len(js)} {e['section']} · {e['title']}", flush=True)
        time.sleep(rooyun.SUBMIT_GAP)
    failed = []
    for e, _, _ in js:
        s = state.get(e["id"]) or {}
        dest = os.path.join(DOCS, e["file"])
        if not s.get("taskId") or os.path.exists(dest):
            continue
        for _ in range(200):
            t = client.task(s["taskId"])
            if t.get("status") in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(3)
        if t.get("status") != "succeeded":
            failed.append(e["title"])
            state.pop(e["id"], None)
            save()
            continue
        client.download(t["assetId"], dest)
    return failed


def mac(items):
    os.makedirs(os.path.join(AUDIO, "mac"), exist_ok=True)
    for e in items:
        if e.get("engine") != "mac":
            continue
        dest = os.path.join(DOCS, e["file"])
        if os.path.exists(dest):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            aiff = os.path.join(tmp, "a.aiff")
            r = subprocess.run(["/usr/bin/say", "-v", e["voice"], "-o", aiff, e["text"]], capture_output=True)
            if r.returncode:
                print("  这台 Mac 没有声音", e["voice"])
                continue
            subprocess.run(["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", "-b", "48000", aiff, dest], check=True)
        print("  Mac", e["voice"])


def page(items):
    present = [dict({k: v for k, v in e.items() if k not in ("voice",)}, ready=os.path.exists(os.path.join(DOCS, e["file"])))
               for e in items]
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(present, f, ensure_ascii=False, indent=1)
    ready = sum(e["ready"] for e in present)
    print(f"gallery.json：{len(present)} 条，已有音频 {ready} 条")


if __name__ == "__main__":
    items = entries()
    if "--mac" in sys.argv:
        mac(items)
    elif "--page" not in sys.argv:
        missing = todo(items)
        if not missing:
            print("如云试听音频都已生成")
        else:
            client = rooyun.Client("https://www.rooyun.com")
            js = jobs(client, missing)
            price, available = client.precheck([{"model": m, "capability": "t2a", "params": {"text": p["text"]}} for _, m, p in js])
            print(f"要生成 {len(js)} 段试听，约 {price} 积分，可用 {round(available, 2)}（约 {round(len(js) * rooyun.SUBMIT_GAP / 60)} 分钟）")
            if "--record" in sys.argv:
                if "--yes" not in sys.argv and input("开始吗？[y/N] ").strip().lower() not in ("y", "yes"):
                    sys.exit("没有生成")
                failed = record(client, js)
                print("全部完成" if not failed else f"{len(failed)} 段没成功，重跑补齐：{failed}")
    page(items)
