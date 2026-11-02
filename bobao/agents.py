"""Claude Code and Codex tell Bobao when they finish a task or wait for you.

    bobao agent install claude|codex   add the hook (Claude Code: ~/.claude/settings.json;
                                       Codex: notify in ~/.codex/config.toml)
    bobao agent claude prompt|stop|notify    run by the Claude Code hook (its JSON on stdin)
    bobao agent codex '<json>'               run by Codex's notify

Each becomes a message to the local webhook ("智能体完成" / "智能体等你确认"); the rules
in packs/rules/bobao.json say what is spoken. A Claude Code turn shorter than
agents.minSeconds stays silent, so quick answers don't talk. A hook never fails or
prints: if Bobao isn't running, the agent carries on as if nothing happened.
"""

import json
import os
import re
import shlex
import shutil
import sys
import time
import urllib.request

from . import config, paths

TURNS = os.path.join(paths.HOME, "agent-turns.json")   # Claude Code session -> when its turn started
CLAUDE_SETTINGS = os.path.expanduser("~/.claude/settings.json")
CODEX_CONFIG = os.path.expanduser("~/.codex/config.toml")


LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 never goes through a proxy


def post(cfg, body):
    w = cfg["sources"]["webhook"]
    req = urllib.request.Request(f"http://127.0.0.1:{w.get('port', 8766)}/notify",
                                 json.dumps(body, ensure_ascii=False).encode(),
                                 {"content-type": "application/json", "x-bobao-secret": w.get("secret") or ""})
    try:
        LOCAL.open(req, timeout=2).read()
    except Exception:
        pass


def project(cwd):
    return os.path.basename((cwd or "").rstrip("/")) or ""


def event(agent, title, cwd):
    return {"channel": agent, "title": title, "fields": {"项目": project(cwd)}}


def claude(kind, data, cfg, now=None):
    """The message for one Claude Code hook call, or None to stay silent."""
    now = now or time.time()
    turns = config.read_json(TURNS, {}) or {}
    sid = data.get("session_id") or ""
    if kind == "prompt":
        turns[sid] = now
        paths.ensure()
        turns = {k: v for k, v in turns.items() if now - v < 86400}
        with open(TURNS, "w") as f:
            json.dump(turns, f)
        return None
    if kind == "stop":
        started = turns.get(sid)
        if started is None or now - started < cfg["agents"].get("minSeconds", 60):
            return None
        return event("Claude Code", "智能体完成", data.get("cwd"))
    msg = data.get("message") or ""
    if re.search(r"permission|批准|确认|approve", msg, re.I):   # not the idle "waiting for your input"
        return event("Claude Code", "智能体等你确认", data.get("cwd"))
    return None


def codex(data):
    if data.get("type") == "agent-turn-complete":
        return event("Codex", "智能体完成", data.get("cwd"))
    return None


def hook(argv):
    """Entry point for the hooks themselves: never raises, never prints."""
    try:
        cfg = config.load()
        if argv[0] == "claude":
            body = claude(argv[1], json.loads(sys.stdin.read() or "{}"), cfg)
        else:
            body = codex(json.loads(argv[-1]))
        if body:
            post(cfg, body)
    except Exception:
        pass


def windows_command():
    """[python, bobao_cli.py]: on Windows, hooks run Python on the installed copy directly."""
    py = sys.executable.replace("\\", "/")
    return [py, os.path.join(paths.APP, "bobao_cli.py").replace("\\", "/")]


def command():
    """The bobao launcher hooks call: the installed copy if there is one (it never moves)."""
    if os.name == "nt":
        return " ".join(f'"{p}"' for p in windows_command())
    installed = os.path.join(paths.APP, "bin", "bobao")
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "bobao")
    return installed if os.path.exists(installed) else here


def install_claude():
    settings = config.read_json(CLAUDE_SETTINGS, {}) or {}
    hooks = settings.setdefault("hooks", {})
    added = []
    for event_name, kind in (("UserPromptSubmit", "prompt"), ("Stop", "stop"), ("Notification", "notify")):
        cmd = f"{command() if os.name == 'nt' else shlex.quote(command())} agent claude {kind}"
        entries = hooks.setdefault(event_name, [])
        if any("agent claude" in h.get("command", "") for e in entries for h in e.get("hooks", [])):
            continue
        entries.append({"hooks": [{"type": "command", "command": cmd, "timeout": 5}]})
        added.append(event_name)
    if not added:
        return "Claude Code 已经接好了"
    if os.path.exists(CLAUDE_SETTINGS):
        shutil.copy(CLAUDE_SETTINGS, CLAUDE_SETTINGS + ".before-bobao")
    os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
    with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return f"已在 {CLAUDE_SETTINGS} 加上 {', '.join(added)} 钩子（原文件备份为 settings.json.before-bobao）。新开的 Claude Code 会话生效"


def install_codex():
    parts = windows_command() if os.name == "nt" else [command()]
    line = "notify = [" + ", ".join(json.dumps(p) for p in parts + ["agent", "codex"]) + "]"
    text = open(CODEX_CONFIG, encoding="utf-8").read() if os.path.exists(CODEX_CONFIG) else ""
    if "agent\", \"codex\"" in text:
        return "Codex 已经接好了"
    if re.search(r"(?m)^\s*notify\s*=", text):
        return f"{CODEX_CONFIG} 里已经有 notify 了，没有改动。想让 Bobao 播报，把那一行换成：\n  {line}"
    os.makedirs(os.path.dirname(CODEX_CONFIG), exist_ok=True)
    with open(CODEX_CONFIG, "w", encoding="utf-8") as f:
        f.write(line + "\n" + text)   # a top-level key must come before any [table]
    return f"已在 {CODEX_CONFIG} 第一行加上 notify。新开的 Codex 会话生效"


def install(which):
    """Adds the hook and turns on what it needs: the webhook, and the rules that speak."""
    user = config.read_json(paths.CONFIG, {}) or {}
    user.setdefault("sources", {}).setdefault("webhook", {})["enabled"] = True
    user.setdefault("agents", {})["enabled"] = True
    config.save_user(user)
    return install_claude() if which == "claude" else install_codex()
