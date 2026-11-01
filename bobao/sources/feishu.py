"""Feishu / Lark groups, read through lark-cli as the user, so cards come with every field
and external groups work. Needs `lark-cli` installed and logged in (lark-cli auth login).

Each group is checked every pollSeconds, and right away when the notification helper
sees a Feishu popup for it. The cursor (message_position) per group is kept in
~/.bobao/state.json, so nothing is read twice and nothing new is skipped, however many
arrive at once.
"""

import json
import os
import shutil
import subprocess
import time

from .. import paths
from ..config import read_json
from ..events import Event, parse_card
from ..log import log

HOME = os.path.expanduser("~")


def lark_cli(cfg):
    return (cfg.get("larkCli") or shutil.which("lark-cli") or f"{HOME}/.local/bin/lark-cli")


def env():
    extra = [f"{HOME}/.local/node/current/bin", "/opt/homebrew/bin", "/usr/local/bin"]
    return dict(os.environ, PATH=":".join(extra + [os.environ.get("PATH", "/usr/bin:/bin")]))


def lark(cfg, *args):
    out = subprocess.run([lark_cli(cfg), *args, "--as", "user"], capture_output=True, text=True, env=env(), timeout=60)
    try:
        data = json.loads(out.stdout)
    except ValueError:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300])
    if not data.get("ok"):
        raise RuntimeError(json.dumps(data.get("error"), ensure_ascii=False)[:300])
    return data["data"]


def to_event(chat, m):
    title, fields, plain = parse_card(str(m.get("content") or ""))
    sender = (m.get("sender") or {}).get("sender_type")
    try:
        sent = time.mktime(time.strptime(m.get("create_time", ""), "%Y-%m-%d %H:%M"))
    except (ValueError, TypeError):
        sent = None
    return Event("feishu", chat, title, plain, fields, bot=None if not sender else sender == "app", time=sent)


class Feishu:
    def __init__(self):
        self.state = read_json(paths.STATE, {}) or {}
        self.ids, self.ids_at = {}, 0

    def chat_ids(self, cfg, names):
        if time.time() - self.ids_at > 3600 or any(n not in self.ids for n in names):
            chats = lark(cfg["sources"]["feishu"], "im", "+chat-list", "--page-all").get("chats") or []
            self.ids = {c["name"]: c["chat_id"] for c in chats}
            self.ids_at = time.time()
            for n in names:
                if n not in self.ids:
                    log(f"找不到飞书群「{n}」，请检查 config.json 里的群名，并确认你在群里")
        return {n: self.ids[n] for n in names if n in self.ids}

    def check(self, cfg, names, handle):
        """Hands every new message to handle(event); returns False if a group could not be read."""
        src, ok = cfg["sources"]["feishu"], True
        for name, chat_id in self.chat_ids(cfg, names).items():
            try:
                msgs = lark(src, "im", "+chat-messages-list", "--chat-id", chat_id, "--order", "desc",
                            "--page-size", "50", "--no-reactions").get("messages") or []
            except Exception as e:
                log(f"读取飞书群「{name}」失败: {e}")
                ok = False
                continue
            msgs = [m for m in msgs if not m.get("deleted") and str(m.get("message_position", "")).isdigit()]
            if not msgs:
                continue
            newest = max(int(m["message_position"]) for m in msgs)
            key = f"feishu:{chat_id}"
            last = self.state.get(key)
            if last is None:   # first sight of this group: start from now, no backlog
                self.state[key] = newest
                self.save()
                log(f"开始监听飞书群「{name}」")
                continue
            for m in sorted((m for m in msgs if int(m["message_position"]) > last), key=lambda m: int(m["message_position"])):
                if m.get("msg_type") == "system":   # "X joined the group" and the like
                    continue
                ev = to_event(name, m)
                if src.get("botsOnly", True) and ev.bot is False:   # people chatting, not notifications
                    continue
                handle(ev)
            if newest > last:
                self.state[key] = newest
                self.save()
        return ok

    def recent(self, cfg, name, limit=30):
        """The last `limit` messages of a group as events, oldest first (for bobao replay)."""
        chat_id = self.chat_ids(cfg, [name]).get(name)
        if not chat_id:
            return []
        msgs = lark(cfg["sources"]["feishu"], "im", "+chat-messages-list", "--chat-id", chat_id, "--order", "desc",
                    "--page-size", str(min(limit, 50)), "--no-reactions").get("messages") or []
        return [(m, to_event(name, m)) for m in reversed(msgs) if m.get("msg_type") != "system"]

    def save(self):
        tmp = paths.STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, paths.STATE)
