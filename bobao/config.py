"""Builds the settings everything else reads, from three layers:

1. rule packs (packs/rules/*.json): which notifications are which type, per platform;
2. a style pack (packs/styles/*.json): what is said for each type, in which voice,
   with which sound, and the playful follow-up lines;
3. the user's ~/.bobao/config.json, which picks the packs and overrides anything.

The user file is re-read on every check, so edits apply without a restart.
"""

import json
import os

from . import paths

DEFAULTS = {
    "称呼": "老板",
    "style": "formal",
    "rulePacks": ["generic"],
    "engine": "mac",            # mac: the Mac's own voice | rooyun: recorded RooYun voices
    "macVoice": "Tingting",
    "rate": 200,
    "platforms": {},            # {"RooYun": {"say": "如云"}}: how a platform name is spoken
    "aliases": {},              # long card values -> short spoken ones
    "values": {},               # {"方式": [...], "套餐": [...]}: what can fill a slot, for recording
    "rules": [],
    "skipTitles": ["模拟", "测试"],
    "catchAll": {},
    "types": {},
    "voices": {},
    "tease": {},
    "bigOrder": {},             # {"BigModel": 100, "*": 1000}: amounts that get the 大单 line
    "maxAgeMinutes": 30,
    "sources": {
        "feishu": {"enabled": False, "chats": [], "botsOnly": True, "pollSeconds": 60},
        "webhook": {"enabled": True, "port": 8766, "secret": ""},
        "notifications": {"enabled": False, "apps": []},
    },
    "rooyun": {"base": "https://www.rooyun.com", "model": "speech-2.8-hd"},
}


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except ValueError as e:
        raise SystemExit(f"{path} 不是合法的 JSON：{e}")


def pack_path(kind, name):
    """A pack by name (packs/<kind>/<name>.json, or ~/.bobao/packs/...) or by path."""
    if name.endswith(".json") or os.sep in name:
        return os.path.expanduser(name)
    for base in (os.path.join(paths.HOME, "packs", kind), os.path.join(paths.PACKS, kind)):
        p = os.path.join(base, name + ".json")
        if os.path.exists(p):
            return p
    raise SystemExit(f"找不到{'风格' if kind == 'styles' else '规则'}包「{name}」")


def list_packs(kind):
    out = {}
    for base in (os.path.join(paths.PACKS, kind), os.path.join(paths.HOME, "packs", kind)):
        if os.path.isdir(base):
            for f in sorted(os.listdir(base)):
                if f.endswith(".json"):
                    out[f[:-5]] = read_json(os.path.join(base, f), {})
    return out


def _merge_values(into, more):
    for k, v in (more or {}).items():
        into[k] = list(dict.fromkeys(into.get(k, []) + list(v)))


def load(user=None):
    user = read_json(paths.CONFIG, {}) if user is None else user
    cfg = json.loads(json.dumps(DEFAULTS))
    for k, v in user.items():
        if k == "sources":
            for s, sv in v.items():
                cfg["sources"].setdefault(s, {}).update(sv)
        elif k != "rules":
            cfg[k] = v

    # Rule packs, in the order listed; the user's own rules go first so they win.
    rules, platforms, aliases, values, catch = list(user.get("rules", [])), {}, {}, {}, {}
    for name in cfg["rulePacks"]:
        pack = read_json(pack_path("rules", name), {})
        rules += pack.get("rules", [])
        platforms.update(pack.get("platforms", {}))
        aliases.update(pack.get("aliases", {}))
        _merge_values(values, pack.get("values"))
        if pack.get("catchAll"):
            catch = pack["catchAll"]
    platforms.update(user.get("platforms", {}))
    aliases.update(user.get("aliases", {}))
    _merge_values(values, user.get("values"))
    cfg.update(rules=rules, platforms=platforms, aliases=aliases, values=values,
               catchAll=user.get("catchAll", catch))

    # Style pack, then the user's per-type and per-voice overrides on top.
    style = read_json(pack_path("styles", cfg["style"]), {})
    cfg["styleName"] = style.get("name", cfg["style"])
    cfg["称呼"] = user.get("称呼") or style.get("称呼") or DEFAULTS["称呼"]
    types = {t: dict(v) for t, v in style.get("types", {}).items()}
    for t, v in user.get("types", {}).items():
        types.setdefault(t, {}).update(v)
    cfg["types"] = types
    cfg["voices"] = dict(style.get("voices", {}), **user.get("voices", {}))
    cfg["sounds"] = dict(style.get("sounds", {}), **user.get("sounds", {}))
    cfg["pick"] = dict(style.get("pick", {}), **user.get("pick", {}))
    cfg["firstOrder"] = user.get("firstOrder", style.get("firstOrder", "新客首单"))
    cfg["bigOrderSay"] = user.get("bigOrderSay", style.get("bigOrderSay", "大单来啦"))
    tease = dict(style.get("tease", {}))
    lines = {k: list(v) for k, v in tease.get("lines", {}).items()}
    for k, v in user.get("tease", {}).get("lines", {}).items():
        lines[k] = list(dict.fromkeys(lines.get(k, []) + v))
    tease.update({k: v for k, v in user.get("tease", {}).items() if k != "lines"}, lines=lines)
    cfg["tease"] = tease
    cfg["health"] = dict(style.get("health", {}), **user.get("health", {}))
    return cfg


def voice_for(cfg, kind):
    """{"voice": id, "emotion": ...} for a type or for "接话" (the follow-up voice)."""
    t = cfg["types"].get(kind, {})
    return t.get("voice") or cfg["voices"].get(kind) or cfg["voices"].get("default") or {"voice": "female-shaonv"}


def voice_key(v):
    return f"{v['voice']}|{v.get('emotion') or ''}"


def save_user(user):
    paths.ensure()
    tmp = paths.CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(user, f, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.CONFIG)
