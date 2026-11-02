"""The background loop: reads every source, decides, speaks.

decide() is the one place an event becomes speech or silence, and every silence of a
matched event is logged with its reason (夜间不播, 冷却中, 过期未播, 已关闭), so what is
not announced can always be traced.
"""

import random
import time

from . import config, compose, events
from .log import log
from .sources import notifications
from .sources.feishu import Feishu, poll_seconds
from .speaker import Speaker

last_spoken = {}   # (rule index, platform) -> time, for cooldownMinutes


def in_hours(span):
    """'00:00-08:00' (may wrap past midnight) contains now?"""
    if not span:
        return False
    start, end = span.split("-")
    now = time.strftime("%H:%M")
    return start <= now < end if start <= end else (now >= start or now < end)


def off_schedule(cfg, t, rule):
    """Why now is outside the schedule for this type, or "" if it may play.
    The global schedule applies unless the type says "always": true; a type's own
    days / hours / quietHours, and a rule's quietHours, apply on top."""
    s = {} if t.get("always") else dict(cfg.get("schedule") or {})
    s.update({k: t[k] for k in ("days", "hours", "quietHours") if t.get(k)})
    if rule.get("quietHours"):
        s["quietHours"] = rule["quietHours"]
    if s.get("days") and time.localtime().tm_wday + 1 not in s["days"]:
        return "今天不在播报日"
    if s.get("hours") and not in_hours(s["hours"]):
        return f"不在播报时段（{s['hours']}）"
    if in_hours(s.get("quietHours")):
        return f"夜间不播（{s['quietHours']}）"
    return ""


def decide(ev, cfg, dry=False, rnd=random):
    """Returns (utterance or None, reason). dry: work out the text only, leaving
    cooldowns and the log alone (for previews, replays and stale messages)."""
    match, why = events.classify(ev, cfg)
    if not match:
        return None, why
    t = compose.type_settings(cfg, match.type)
    if t.get("enabled") is False:
        return None, f"{match.type}已关闭"
    why = off_schedule(cfg, t, match.rule)
    if not dry and why:
        return None, why
    stale = cfg.get("maxAgeMinutes")
    if not dry and ev.time and stale and time.time() - ev.time > stale * 60:
        utt = compose.render(match, ev, cfg, rnd)
        return None, f"过期未播：{utt['text'] if utt else ev.title}"
    cooldown = match.rule.get("cooldownMinutes") or t.get("cooldownMinutes") or 0
    key = (match.index, match.platform)
    if not dry and time.time() - last_spoken.get(key, 0) < cooldown * 60:
        return None, f"冷却中（{cooldown} 分钟内同类只播一次）"
    utt = compose.render(match, ev, cfg, rnd)
    if not utt:
        return None, f"{match.type}没有说法"
    if not dry:
        last_spoken[key] = time.time()
        if match.index == -2 or match.rule.get("catchAll"):   # a rule can be a catch-all too
            log(f"未知通知类型（建议加一条规则）[{ev.source}:{ev.channel}] {ev.title}")
    utt["match"] = match
    return utt, ""


def run():
    speaker = Speaker()
    feishu, spool = Feishu(), notifications.Spool()
    state = {"cfg": config.load()}
    log("Bobao 开始运行")

    def handle(ev, dry=False):
        cfg = state["cfg"]
        utt, why = decide(ev, cfg, dry=dry)
        label = f"[{ev.source}{':' + ev.channel if ev.channel else ''}] {ev.title}"
        if not utt:
            if not dry and (why != "没有规则" or ev.source == "webhook"):
                log(f"不播 {label}：{why}")
            return {"spoken": False, "reason": why}
        if not dry:
            log(f"播报 {label} → {utt['text']}")
            speaker.put(utt, cfg)
        return {"spoken": not dry, "type": utt["type"], "text": utt["text"]}

    web = None
    next_feishu, failing_since, warned = 0, None, False
    while True:
        try:
            state["cfg"] = cfg = config.load()
        except SystemExit as e:   # a broken config.json: keep the last good one
            log(str(e))
            cfg = state["cfg"]
        src = cfg["sources"]
        try:
            if src["webhook"].get("enabled") and not web:
                from .sources import webhook
                web = webhook.serve(int(src["webhook"].get("port", 8766)), lambda: state["cfg"], handle)
            nudged = set()
            for n in spool.read():
                if n.get("nudge") or (notifications.is_lark(n.get("app", "")) and n.get("title") in src["feishu"].get("chats", [])):
                    nudged.add(n.get("title"))
                elif src["notifications"].get("enabled"):
                    handle(notifications.to_event(n))
            fs = src["feishu"]
            if fs.get("enabled") and (fs.get("chats") or fs.get("profile")):
                groups = feishu.groups(cfg)
                if time.time() >= next_feishu:
                    ok = feishu.check(cfg, groups, handle)
                    next_feishu = time.time() + poll_seconds(fs)
                    failing_since, warned = health(cfg, speaker, ok, failing_since, warned)
                else:
                    pushed = feishu.pushed(cfg)
                    if pushed:
                        feishu.check(cfg, sorted(pushed), handle)
                    elif nudged & set(groups):
                        time.sleep(1)   # let the message settle on Feishu's side
                        feishu.check(cfg, sorted(nudged & set(groups)), handle)
                        next_feishu = min(next_feishu, time.time() + 5)   # the popup can beat the API
        except Exception as e:
            log(f"出错，稍后重试: {e}")
            next_feishu = time.time() + 30
        time.sleep(1)


def health(cfg, speaker, ok, failing_since, warned):
    """After `health.minutes` of failed reads, say so once; when reads work again, say that."""
    h = cfg["health"]
    if ok:
        if warned and h.get("back"):
            log("读取恢复正常")
            speaker.put({"sound": cfg["sounds"].get("恢复"), "text": "",
                         "segments": [(config.voice_for(cfg, "恢复"), compose.fill(random.choice(h["back"]), cfg))]}, cfg)
        return None, False
    failing_since = failing_since or time.time()
    if not warned and h.get("say") and time.time() - failing_since >= h.get("minutes", 5) * 60:
        log("连续读取失败，播报提醒")
        speaker.put({"sound": cfg["sounds"].get("告警"), "text": "",
                     "segments": [(config.voice_for(cfg, "告警"), compose.fill(random.choice(h["say"]), cfg))]}, cfg)
        warned = True
    return failing_since, warned
