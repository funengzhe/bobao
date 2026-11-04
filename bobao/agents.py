"""Any coding agent tells Bobao when it finishes a task or waits for you.

    bobao agent done [--name Cursor]      a task is finished (run by the agent's own hook)
    bobao agent waiting [--name Cursor]   it waits for your approval
    bobao agent install claude|codex      ready-made hooks for Claude Code and Codex
    bobao agent setup [--name X]          the command to put in any other agent's hook
    bobao agent watch --name X --dir D    no hook at all: watch the folder its sessions are saved in

Agents differ: Claude Code has hooks, Codex a notify command, Cursor and others their own
hook files. The agent that installs Bobao wires its own mechanism to `bobao agent done`
(AGENTS.md says how); Claude Code and Codex have presets here:
    bobao agent claude prompt|stop|notify|failure|ask    run by the Claude Code hooks (JSON on stdin)
    bobao agent codex '<json>'               run by Codex's notify

Each becomes a message to the local webhook ("智能体完成", "智能体等你确认", and from Claude
Code also how long it took, a question for you, an API error, the quota back); the rules
in packs/rules/bobao.json say what is spoken. A Claude Code turn shorter than
agents.minSeconds stays silent, so quick answers don't talk. So does one in a session another
session started (its report goes to that one), and one whose own started sessions are still
working: the app wakes it again when they finish, and that last stop is the one you hear. A hook never fails or
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
from datetime import datetime

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


# A turn the app starts itself (a child session's report, CI, a background task finishing)
# continues the work you asked for: its length counts from your last own message.
AUTO = re.compile(r"\s*(Another Claude session sent a message|<cross-session|<side-sessions-event>|"
                  r"<ci-monitor-event>|<task-notification>)")
REMINDER = re.compile(r"\s*<system-reminder>.*?</system-reminder>", re.S)   # the app may put one first
STRETCH = 3 * 3600   # unless that message is this old: then it is new work
HOLD = 20   # seconds a "done" waits: another session (or the app) often picks up right away
LONG, VERY_LONG = 10 * 60, 30 * 60   # a turn this long gets "忙了好一阵" / "熬了好久"
NEEDS_YOU = ("elicitation_dialog", "elicitation_url_dialog", "agent_needs_input")
QUOTA = ("rate_limit", "billing_error", "account_on_hold")
LOGIN = ("authentication_failed", "oauth_org_not_allowed", "cloud_credential_error")


LINKED = re.compile(r"Linked sessions now \(status, not an instruction\):(.*?)(?:\. To message|</system-reminder>)", re.S)
SCAN = 64 << 20   # read at most this much of a transcript, from the end


def stamp(e):
    try:
        return datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def prompts_of(path):
    """From a Claude Code transcript, newest first: (who started the turn, when) for each turn,
    whether a session this one started is still working, and who started its very first turn.
    who: human, sdk (another session started this one), peer (another session's message),
    task_notification, scheduled. None when the transcript can't be read."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            first = None
            for line in f.read(1 << 16).splitlines():
                e = loads(line)
                if e and is_prompt(e):
                    first = e.get("turnOrigin")
                    break
            turns, working, linked, tail, pos = [], False, None, b"", size
            while pos > 0 and size - pos < SCAN:
                step = min(1 << 20, pos)
                pos -= step
                f.seek(pos)
                lines = (f.read(step) + tail).split(b"\n")
                tail = lines.pop(0) if pos > 0 else b""
                for line in reversed(lines):
                    if b'"turnOrigin"' not in line and b'"tool_use"' not in line:
                        continue
                    e = loads(line)
                    if not e:
                        continue
                    if linked is None and e.get("type") == "assistant":
                        for c in (e.get("message") or {}).get("content") or []:
                            if isinstance(c, dict) and c.get("type") == "tool_use" and wakes(c.get("name", ""), c.get("input") or {}):
                                working = True   # started or messaged after the last status note
                    if not is_prompt(e):
                        continue
                    turns.append((e.get("turnOrigin"), stamp(e)))
                    if linked is None:
                        m = LINKED.search(text_of(e))
                        if m:
                            linked = m.group(1)
                            working = working or bool(re.search(r"\((working|starting)", linked))
                    asked = [w for w, _ in turns if w != "task_notification"]
                    if "human" in asked or (first == "sdk" and asked):   # older notes are stale
                        return {"first": first, "turns": turns, "working": working}
            return {"first": first, "turns": turns, "working": working}
    except Exception:
        return None


def wakes(name, args):
    """This tool call sets another session working: starting one, or messaging it."""
    if name.endswith("start_session"):
        return args.get("initiation") == "user_asked" or bool(args.get("proposal_id"))
    return name in ("SendMessage", "mcp__ccd_session_mgmt__send_message") and "local_" in str(args)


def loads(line):
    try:
        e = json.loads(line)
        return e if isinstance(e, dict) else None
    except Exception:
        return None


def text_of(e):
    c = (e.get("message") or {}).get("content")
    return c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))


def is_prompt(e):
    c = (e.get("message") or {}).get("content")
    return (e.get("type") == "user" and bool(e.get("turnOrigin"))
            and not (isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)))


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
    if kind == "prompt":   # also turns the app starts itself, e.g. a child session's report
        prompt = said = data.get("prompt") or ""
        while REMINDER.match(said):
            said = said[REMINDER.match(said).end():]
        auto = bool(AUTO.match(said) or (said != prompt and not said.strip()))   # or only the app's notes
        if not (auto and now - turns.get(sid, 0) < STRETCH):
            turns[sid] = now
        paths.ensure()
        turns = {k: v for k, v in turns.items() if now - v < 86400}
        with open(TURNS, "w") as f:
            json.dump(turns, f)
        return {"busy": True, "session": sid, "auto": auto}   # drops this session's "done" still waiting
    started = turns.get(sid)
    if kind == "stop":
        seen = prompts_of(data.get("transcript_path") or "")
        if seen and seen["turns"]:
            asked = [w for w, _ in seen["turns"] if w != "task_notification"]
            if seen["first"] == "sdk" and (asked or [None])[0] != "human":
                return None   # a session another one started: its report goes there, not to you
            if seen["working"] and not asks(data.get("last_assistant_message")):
                return None   # sessions it started are still at it; the app wakes it when they finish
            mine = next((t for w, t in seen["turns"] if w == "human" and t), None)
            started = mine if mine and now - mine < STRETCH else seen["turns"][0][1] or started
    took = None if started is None else now - started
    long_enough = took is not None and took >= cfg["agents"].get("minSeconds", 60)
    if kind == "stop":
        if not long_enough or data.get("background_tasks"):   # paused for background work, not done
            return None
        if asks(data.get("last_assistant_message")):
            return dict(event("Claude Code", "智能体提问", cwd), hold=HOLD, session=sid)
        title = "智能体完成·很久" if took >= VERY_LONG else "智能体完成·久" if took >= LONG else "智能体完成"
        return dict(event("Claude Code", title, cwd), hold=HOLD, session=sid)
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


def generic(kind, name="", cwd=None, cfg=None):
    """bobao agent done / waiting, from any agent's hook. An agent heard for the first time
    joins agents.used, so its name gets recorded with the next `bobao voice record`."""
    if name and name not in ((cfg or {}).get("agents") or {}).get("used", []):
        turn_on(name)
    return event(name or "智能体", "智能体完成" if kind == "done" else "智能体等你确认", cwd or os.getcwd())


def hook(argv, name=""):
    """Entry point for the hooks themselves: never raises, never prints."""
    try:
        cfg = config.load()
        if argv[0] in ("done", "waiting"):
            body = generic(argv[0], name, cfg=cfg)
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


def setup_text(name=""):
    """For any other agent: the command its hook should run."""
    turn_on(name)
    cmd = command() if os.name == "nt" else shlex.quote(command())
    who = name or "你的名字"
    return (f"智能体播报已打开{'（' + name + '）' if name else ''}。在你的「任务结束时运行命令」的设置里（钩子、通知、hooks.json 之类）填：\n"
            f"  任务做完：{cmd} agent done --name {who}\n"
            f"  等你确认：{cmd} agent waiting --name {who}\n"
            "命令要很快返回，Bobao 没在运行时它什么也不做。\n"
            f"没有这种设置的话，看看你的会话记录是不是存成文件：bobao agent watch --name {who} --dir 会话目录")


def watch(name, folder, idle=None, done=None, off=False):
    """Adds (or with off removes) a session folder to watch for an agent without hooks."""
    from .sources.sessions import snapshot
    user = config.read_json(paths.CONFIG, {}) or {}
    watches = [w for w in (user.get("agents") or {}).get("watch", []) if w.get("name") != name]
    if off:
        user.setdefault("agents", {})["watch"] = watches
        config.save_user(user)
        return f"不再看 {name} 的会话文件"
    folder = os.path.abspath(os.path.expanduser(folder or ""))
    if not os.path.isdir(folder):
        raise SystemExit(f"没有这个文件夹：{folder}")
    if done:
        re.compile(done)
    files = snapshot(folder)
    if not files:
        raise SystemExit(f"{folder} 里没有文件。会话记录不在这里？")
    newest = max(files, key=lambda p: files[p][1])
    w = {"name": name, "dir": folder}
    if idle:
        w["idle"] = idle
    if done:
        w["done"] = done
    turn_on(name)
    user = config.read_json(paths.CONFIG, {}) or {}
    user["agents"]["watch"] = watches + [w]
    config.save_user(user)
    ago = int(time.time() - files[newest][1])
    return (f"开始看 {name} 的会话文件：{folder}（{len(files)} 个文件，最近写入的是 {os.path.relpath(newest, folder)}，{ago} 秒前）。\n"
            f"文件停止增长 {idle or 15} 秒算这一轮做完" + (f"，而且结尾要符合 {done}" if done else "") +
            "。这一轮你回复完以后，最近写入的应该就是这次的会话；不是的话目录选错了。\n"
            "已经在用别的办法（钩子、每轮手动喊一声）的话去掉那个，免得念两遍。")
