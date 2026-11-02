"""Any coding agent tells Bobao when it finishes a task or waits for you.

    bobao agent done [--name Cursor]      a task is finished (run by the agent's own hook)
    bobao agent waiting [--name Cursor]   it waits for your approval
    bobao agent install claude|codex      ready-made hooks for Claude Code and Codex
    bobao agent setup                     the command to put in any other agent's hook

Agents differ: Claude Code has hooks, Codex a notify command, Cursor and others their own
hook files. The agent that installs Bobao wires its own mechanism to `bobao agent done`
(AGENTS.md says how); Claude Code and Codex have presets here:
    bobao agent claude prompt|stop|notify|failure|ask    run by the Claude Code hooks (JSON on stdin)
    bobao agent codex '<json>'               run by Codex's notify

Each becomes a message to the local webhook ("智能体完成", "智能体等你确认", and from Claude
Code also how long it took, a question for you, an API error, the quota back); the rules
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


LONG, VERY_LONG = 10 * 60, 30 * 60   # a turn this long gets "忙了好一阵" / "熬了好久"
NEEDS_YOU = ("elicitation_dialog", "elicitation_url_dialog", "agent_needs_input")
QUOTA = ("rate_limit", "billing_error", "account_on_hold")
LOGIN = ("authentication_failed", "oauth_org_not_allowed", "cloud_credential_error")


def asks(text):
    """Claude's last words end in a question: it stopped to ask you something."""
    return bool(re.search(r"[?？]$", re.sub(r"[\s*_`)）]+$", "", text or "")))


def claude(kind, data, cfg, now=None):
    """The message for one Claude Code hook call, or None to stay silent.
    prompt: a turn starts. stop: it ended (done, or a question for you). notify: approval,
    a question in a dialog, the quota coming back. failure: it stopped on an API error.
    ask: it opened a multiple-choice question (AskUserQuestion)."""
    now = now or time.time()
    turns = config.read_json(TURNS, {}) or {}
    sid = data.get("session_id") or ""
    cwd = data.get("cwd")
    if kind == "prompt":
        turns[sid] = now
        paths.ensure()
        turns = {k: v for k, v in turns.items() if now - v < 86400}
        with open(TURNS, "w") as f:
            json.dump(turns, f)
        return None
    started = turns.get(sid)
    took = None if started is None else now - started
    long_enough = took is not None and took >= cfg["agents"].get("minSeconds", 60)
    if kind == "stop":
        if not long_enough or data.get("background_tasks"):   # paused for background work, not done
            return None
        if asks(data.get("last_assistant_message")):
            return event("Claude Code", "智能体提问", cwd)
        title = "智能体完成·很久" if took >= VERY_LONG else "智能体完成·久" if took >= LONG else "智能体完成"
        return event("Claude Code", title, cwd)
    if kind == "ask":
        return event("Claude Code", "智能体提问", cwd) if long_enough else None
    if kind == "failure":
        err = data.get("error") or ""
        title = "智能体出错·额度" if err in QUOTA else "智能体出错·登录" if err in LOGIN else "智能体出错"
        return event("Claude Code", title, cwd)
    kind_of = data.get("notification_type") or ""
    if kind_of == "permission_prompt" or (not kind_of and re.search(r"permission|批准|确认|approve",
                                                                     data.get("message") or "", re.I)):
        return event("Claude Code", "智能体等你确认", cwd)   # not the idle "waiting for your input"
    if kind_of in NEEDS_YOU:
        return event("Claude Code", "智能体提问", cwd)
    if kind_of == "quota_auto_resume_fired":
        return event("Claude Code", "智能体额度恢复", cwd)
    return None


def codex(data):
    if data.get("type") == "agent-turn-complete":
        return event("Codex", "智能体完成", data.get("cwd"))
    return None


def generic(kind, name="", cwd=None):
    """bobao agent done / waiting, from any agent's hook."""
    return event(name or "智能体", "智能体完成" if kind == "done" else "智能体等你确认", cwd or os.getcwd())


def hook(argv, name=""):
    """Entry point for the hooks themselves: never raises, never prints."""
    try:
        cfg = config.load()
        if argv[0] in ("done", "waiting"):
            body = generic(argv[0], name)
        elif argv[0] == "claude":
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


CLAUDE_HOOKS = [("UserPromptSubmit", "prompt", ""), ("Stop", "stop", ""), ("Notification", "notify", ""),
                ("StopFailure", "failure", ""), ("PreToolUse", "ask", "AskUserQuestion")]


def install_claude():
    settings = config.read_json(CLAUDE_SETTINGS, {}) or {}
    hooks = settings.setdefault("hooks", {})
    added = []
    for event_name, kind, matcher in CLAUDE_HOOKS:
        cmd = f"{command() if os.name == 'nt' else shlex.quote(command())} agent claude {kind}"
        entries = hooks.setdefault(event_name, [])
        if any(f"agent claude {kind}" in h.get("command", "") for e in entries for h in e.get("hooks", [])):
            continue
        entry = {"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        entries.append(entry)
        added.append(event_name)
    if not added:
        return "Claude Code 已经接好了"
    if os.path.exists(CLAUDE_SETTINGS) and not os.path.exists(CLAUDE_SETTINGS + ".before-bobao"):
        shutil.copy(CLAUDE_SETTINGS, CLAUDE_SETTINGS + ".before-bobao")   # keep the one from before Bobao
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


def turn_on(agent=""):
    """What the announcements need: the webhook, and the rules that speak. agent joins
    agents.used, so with recorded voices only the agents set up here are recorded."""
    user = config.read_json(paths.CONFIG, {}) or {}
    user.setdefault("sources", {}).setdefault("webhook", {})["enabled"] = True
    agents = user.setdefault("agents", {})
    agents["enabled"] = True
    if agent and agent not in agents.setdefault("used", []):
        agents["used"].append(agent)
    config.save_user(user)


def install(which):
    turn_on("Claude Code" if which == "claude" else "Codex")
    return install_claude() if which == "claude" else install_codex()


def setup_text():
    """For any other agent: the command its hook should run."""
    turn_on()
    cmd = command() if os.name == "nt" else shlex.quote(command())
    return (f"智能体播报已打开。在你的智能体「任务结束时运行命令」的设置里（钩子、通知、hooks.json 之类）填：\n"
            f"  任务做完：{cmd} agent done --name 智能体名字\n"
            f"  等你确认：{cmd} agent waiting --name 智能体名字\n"
            "命令要很快返回，Bobao 没在运行时它什么也不做。")
