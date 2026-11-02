"""What to say for a classified event, and everything that could ever be said.

A template is a sentence with slots, e.g. "{开头}，{平台}到账 {金额}啦，{方式}，{结尾}".
render() fills it for one event. plan() fills it every possible way, so all of it can
be recorded once: a part between commas is recorded whole, except around an amount,
where the words before it, the number words and the unit with what follows it are
recorded separately and stitched at play time.
"""

import random
import re

from .config import AGENT_NAMES, needed, voice_for
from .numbers import UNITS, money, amount_of

WHOLE_LIMIT = 40   # a template with at most this many fillings is recorded sentence by sentence
SLOT = re.compile(r"\{([^{}]+)\}")
AMOUNT = "\x00"


def spoken_platform(cfg, p):
    return (cfg["platforms"].get(p) or {}).get("say", p) if p else ""


def agent_names(cfg):
    return {**AGENT_NAMES, **(cfg.get("agents") or {}).get("names", {})}


def recorded_agents(cfg):
    """The agent names to record: those set up here (agents.used), else every known one and 智能体."""
    names, used = agent_names(cfg), (cfg.get("agents") or {}).get("used")
    if used:
        return sorted({names.get(u, u) for u in used})
    return sorted(set(names.values())) + ["智能体"]


def spoken_agent(cfg, name):
    """'Claude Code' -> 'Claude'. A name nobody recorded is read as 智能体 with recorded voices."""
    names = agent_names(cfg)
    if name in names:
        return names[name]
    return name if name and cfg["engine"] != "rooyun" else "智能体"


def alias(cfg, value):
    for long, short in cfg["aliases"].items():
        value = value.replace(long, short)
    return value


def card_values(ev, rule, cfg):
    """金额 / 方式 / 套餐 / 首单 from the event's fields."""
    names = rule.get("fields") or {}
    out = {}
    for slot, hint in (("金额", "金额"), ("方式", "方式"), ("套餐", "套餐")):
        key = names.get(slot) or next((k for k in ev.fields if hint in k), None)
        if key and ev.fields.get(key):
            v = ev.fields[key]
            out[slot] = re.split(r"[（(]", v)[0].strip() if slot == "金额" else alias(cfg, v.strip())
    if ev.fields.get("金额") is None and "金额" not in out and isinstance(ev.fields.get("amount"), (int, float, str)):
        out["金额"] = str(ev.fields["amount"])
    out["首单"] = any("首次" in str(v) or "首充" in str(v) or "首单" in str(v) for v in ev.fields.values())
    return out


def known(cfg, slot, value):
    """With recorded voices, a payment method or plan nobody recorded is left out rather
    than read by a different voice; list it in "values" to have it recorded and read."""
    if cfg["engine"] != "rooyun" or value in cfg["values"].get(slot, []):
        return value
    return ""


def fill(template, values):
    for _ in range(3):   # pick values may hold slots themselves ({开头} -> "{称呼}")
        template = SLOT.sub(lambda m: str(values.get(m.group(1), "")), template)
    return template


def tidy(text):
    text = re.sub(r"https?://\S+", "", text)
    parts = [re.sub(r"\s+", " ", p).strip() for p in text.split("，")]
    return "，".join(p for p in parts if p)


def type_settings(cfg, kind):
    return cfg["types"].get(kind, {})


def render(match, ev, cfg, rnd=random):
    """Returns {"sound", "segments": [(voice, text)], "text"} or None if this type is off."""
    t = type_settings(cfg, match.type)
    if t.get("enabled") is False:
        return None
    say = match.rule.get("say") or t.get("say")
    if not say:
        return None
    card = card_values(ev, match.rule, cfg)
    amount = amount_of(card.get("金额"))
    if match.type in ("收款", "套餐") and amount is None:   # no amount to read: say only that something came in
        say = type_settings(cfg, "通知").get("say")
        if not say:
            return None
    limit = cfg["bigOrder"].get(match.platform, cfg["bigOrder"].get("*"))
    big = match.type in ("收款", "套餐") and limit is not None and amount is not None and amount >= limit
    values = {
        "称呼": cfg["称呼"], "平台": spoken_platform(cfg, match.platform), "名称": match.name or "",
        "平台的": spoken_platform(cfg, match.platform) + "的" if match.platform else "",
        "金额": money(card.get("金额", "")), "方式": known(cfg, "方式", card.get("方式", "")),
        "套餐": known(cfg, "套餐", card.get("套餐", "")),
        "首单": cfg["firstOrder"] if card["首单"] else "", "大单": cfg["bigOrderSay"] if big else "",
        "智能体": spoken_agent(cfg, ev.channel if ev.source == "webhook" else ""),
    }
    values.update({k: rnd.choice(v) for k, v in cfg["pick"].items() if v})
    template = rnd.choice(say) if isinstance(say, list) else say
    segments = [(voice_for(cfg, match.type), tidy(fill(template, values)))]
    tease = cfg["tease"]
    if t.get("tease", True) and tease.get("lines"):
        kind = "大单" if big and tease["lines"].get("大单") else match.type
        lines = tease["lines"].get(kind, []) + tease["lines"].get(f"{kind}·{match.platform}", [])
        if lines and rnd.random() < tease.get("chance", 0):
            segments.append((voice_for(cfg, "接话"), tidy(fill(rnd.choice(lines), values))))
    sound = match.rule.get("sound") or t.get("sound") or cfg["sounds"].get(match.type)
    return {"type": match.type, "sound": sound, "segments": segments,
            "text": "｜".join(s for _, s in segments)}


# ---- planning: every phrase a configuration can say -------------------------

def expand(text, domains):
    """All strings a template can become, each slot taking every value of its domain."""
    m = SLOT.search(text)
    if not m:
        return [text]
    out = []
    for v in domains.get(m.group(1)) or [""]:
        out += expand(text[:m.start()] + v + text[m.end():], domains)
    return out


def contexts(cfg, kind):
    """(platforms, name, the rule's own templates or None) the rules of a type can produce."""
    names = list(cfg["platforms"])
    out = []
    for r in cfg["rules"]:
        if r.get("type") == kind and not r.get("skip") and needed(cfg, r):
            say = r.get("say")
            out.append(([r["platform"]] if r.get("platform") else names + [""], r.get("name") or "",
                        ([say] if isinstance(say, str) else say) if say else None))
    if kind == "通知" or not out:
        out.append((names + [""], "", None))
    return out


def plan(cfg):
    """{voice key: {"voice": v, "phrases": [text...], "numbers": bool}} for everything sayable."""
    from .config import voice_key
    out = {}

    def want(voice, text, numbers=False):
        e = out.setdefault(voice_key(voice), {"voice": voice, "phrases": [], "numbers": False})
        text = re.sub(r"\s+", " ", text).strip()
        if text and text not in e["phrases"]:
            e["phrases"].append(text)
        e["numbers"] = e["numbers"] or numbers

    picks = {k: list(v) for k, v in cfg["pick"].items()}
    for kind in cfg["types"]:
        t = type_settings(cfg, kind)
        if t.get("enabled") is False or not t.get("say"):
            continue
        voice = voice_for(cfg, kind)
        templates = t["say"] if isinstance(t["say"], list) else [t["say"]]
        money_kind = kind in ("收款", "套餐")
        for platforms, name, own in contexts(cfg, kind):
            domains = dict(picks, 称呼=[cfg["称呼"]], 平台=[spoken_platform(cfg, p) for p in platforms], 名称=[name],
                           平台的=[spoken_platform(cfg, p) + "的" if p else "" for p in platforms],
                           金额=[AMOUNT], 方式=cfg["values"].get("方式", []) + [""], 套餐=cfg["values"].get("套餐", []) + [""],
                           首单=[cfg["firstOrder"], ""] if money_kind else [""], 大单=[cfg["bigOrderSay"], ""] if money_kind else [""],
                           智能体=recorded_agents(cfg))
            for template in own or templates:
                whole = [tidy(x) for x in expand(template, domains)] if "{金额}" not in template else []
                if whole and len(whole) <= WHOLE_LIMIT:   # few enough to record each sentence in one take
                    for text in whole:
                        want(voice, text)
                    continue
                for part in template.split("，"):
                    for text in expand(part, domains):
                        if AMOUNT in text:
                            before, after = text.split(AMOUNT, 1)
                            want(voice, before)
                            for unit in UNITS + [""]:
                                want(voice, unit + after)
                            want(voice, "", numbers=True)
                        else:
                            want(voice, text)
        lines = cfg["tease"].get("lines", {})
        if t.get("tease", True) and cfg["tease"].get("chance"):
            pools = [k for k in lines if k == kind or k.startswith(kind + "·") or (money_kind and k.startswith("大单"))]
            for k in pools:
                for line in lines[k]:
                    for text in expand(line, {"称呼": [cfg["称呼"]], "平台": [spoken_platform(cfg, p) for p in cfg["platforms"]] + [""]}):
                        want(voice_for(cfg, "接话"), text)
    for r in cfg.get("reminders") or []:
        want(voice_for(cfg, "提醒"), tidy(fill(r["say"], {"称呼": cfg["称呼"]})))
    for key, kind in (("say", "告警"), ("back", "恢复")):
        for line in cfg["health"].get(key, []):
            want(voice_for(cfg, kind), fill(line, {"称呼": cfg["称呼"]}))
    return out
