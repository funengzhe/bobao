"""A notification from any source, and the rules that decide what kind it is.

Every source (Feishu, webhook, system notifications) turns what it reads into an
Event. classify() then walks the rules top to bottom; the first rule that matches
names the event's type (收款, 告警, ...) and platform, or says to skip it. An event
no rule matches stays silent, unless it looks important (catchAll keywords), in
which case it is announced as a generic 通知 and logged so a rule can be added.
"""

import json
import re

TYPES = ["收款", "套餐", "注册", "日报", "告警", "恢复", "提醒", "通知"]


class Event:
    def __init__(self, source, channel="", title="", text="", fields=None, bot=None, time=None,
                 type=None, platform=None, name=None):
        self.source = source      # feishu | webhook | notifications
        self.channel = channel    # group name, app bundle id, webhook "channel"
        self.title = title or ""
        self.text = text or ""
        self.fields = fields or {}
        self.bot = bot            # True: sent by a bot/app; False: a person; None: unknown
        self.time = time          # epoch seconds when sent, if known
        self.type, self.platform, self.name = type, platform, name   # webhook may give these directly

    def haystack(self):
        return " ".join([self.title, self.text] + [f"{k} {v}" for k, v in self.fields.items()])

    def __repr__(self):
        return f"Event({self.source}:{self.channel} {self.title!r})"


def parse_card(content):
    """Feishu message content -> (title, fields, plain text), for cards and text alike."""
    m = re.match(r'\s*<card title="([^"]*)">(.*?)(</card>)?\s*$', content, re.S)
    if m:
        title, body = m.group(1), m.group(2)
    else:
        title, body = content.strip().split("\n")[0], content
    fields = {}
    for line in body.split("\n"):
        kv = re.match(r"\s*([^：:\n]{1,12})[：:]\s*(.+?)\s*$", line)
        if kv:
            fields[kv.group(1).strip()] = kv.group(2)
    return title, fields, re.sub(r"<[^>]+>", " ", content)


def _any(words, text):
    words = [words] if isinstance(words, str) else words
    return any(w in text for w in words)


def matches(rule, ev, name=""):
    """name fills {称呼} in the words, so "@{称呼}" catches "@小王" in a popup."""
    when = rule.get("when", {})
    if name and "{称呼}" in json.dumps(when, ensure_ascii=False):
        when = json.loads(json.dumps(when, ensure_ascii=False).replace("{称呼}", name))
    if "source" in when and ev.source not in _list(when["source"]):
        return False
    if "channel" in when and ev.channel not in _list(when["channel"]):
        return False
    if "app" in when and not any(a.lower() in ev.channel.lower() for a in _list(when["app"])):
        return False   # a popup's app id, by any part of it: "wework", "lark", "wechat"
    if "title" in when and not _any(when["title"], ev.title):
        return False
    if "text" in when and not _any(when["text"], ev.haystack()):
        return False
    if "not" in when and _any(when["not"], ev.haystack()):
        return False
    return bool(when)   # a rule with no conditions matches nothing, not everything


def _list(v):
    return [v] if isinstance(v, str) else list(v)


def detect_platform(ev, platforms):
    """'[我的店] 充值到账' -> '我的店', or the first known platform named in the title."""
    m = re.match(r"\s*[\[【]([^\]】]+)[\]】]", ev.title)
    if m and m.group(1) in platforms:
        return m.group(1)
    return next((p for p in platforms if p in ev.title), "")


def on_its_channel(rule, ev, cfg):
    """A platform's rules only fire in that platform's own groups, when the user listed them
    (platforms.X.channels), so one platform's alert words never trigger in another's group."""
    channels = (cfg["platforms"].get(rule.get("platform")) or {}).get("channels")
    return not channels or ev.source == "notifications" or ev.channel in channels


class Match:
    def __init__(self, type, platform, name, rule, index):
        self.type, self.platform, self.name, self.rule, self.index = type, platform, name, rule, index

    def __repr__(self):
        return f"Match({self.type} {self.platform} {self.name or ''} rule#{self.index})"


def classify(ev, cfg):
    """Returns (Match or None, reason). reason says why an event stays silent."""
    if _any(cfg.get("skipTitles", []), ev.title):
        return None, "标题含跳过词"
    if ev.type:   # the sender already said what it is (webhook)
        if ev.type not in TYPES:
            return None, f"未知类型 {ev.type}"
        return Match(ev.type, ev.platform or detect_platform(ev, cfg["platforms"]), ev.name, {}, -1), ""
    for i, rule in enumerate(cfg["rules"]):
        if not matches(rule, ev, cfg.get("称呼", "")) or not on_its_channel(rule, ev, cfg):
            continue
        if rule.get("skip"):
            return None, f"规则 #{i + 1} 跳过"
        platform = rule.get("platform") or ev.platform or detect_platform(ev, cfg["platforms"])
        return Match(rule["type"], platform, rule.get("name"), rule, i), ""
    catch = cfg.get("catchAll") or {}
    if catch.get("keywords") and _any(catch["keywords"], ev.haystack()) and ev.source in catch.get("sources", [ev.source]):
        return Match("通知", detect_platform(ev, cfg["platforms"]), None, {"cooldownMinutes": catch.get("cooldownMinutes", 10)}, -2), ""
    return None, "没有规则"
