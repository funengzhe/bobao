"""Feishu / Lark groups, read through lark-cli. Cards come with every field and external
groups work.

Two ways in:
- as your own 飞书播报 bot (recommended; `bobao feishu login`): a self-built Feishu app
  whose bot you add to the groups to announce. It reads only those groups, needs no
  personal login, and its long connection pushes each new message, so a group is
  checked the moment something arrives. sources.feishu.profile names its lark-cli profile.
- as yourself (no profile): lark-cli logged in with `lark-cli auth login`; groups are
  checked every pollSeconds and when the notification helper sees a Feishu popup.

Every group is also checked every pollSeconds (5 minutes with a bot, else 1) and each time
the push connection comes back, since Feishu does not resend what was pushed while it was
down. The cursor (message_position) per group is kept in ~/.bobao/state.json, so nothing
is read twice and nothing new is skipped, however many arrive at once.
"""

import json
import os
import queue
import shutil
import subprocess
import threading
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
    return dict(os.environ, PATH=os.pathsep.join(extra + [os.environ.get("PATH", "/usr/bin:/bin")]))


def identity(src):
    """lark-cli flags and --as for a source: its bot when it names a profile, else the user."""
    profile = src.get("profile")
    return (["--profile", profile] if profile else []), ("bot" if profile else "user")


def poll_seconds(src):
    return src.get("pollSeconds") or (300 if src.get("profile") else 60)


def lark(src, *args, stdin=None):
    flags, who = identity(src)
    out = subprocess.run([lark_cli(src), *flags, *args, "--as", who], input=stdin,
                         capture_output=True, text=True, env=env(), timeout=60)
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


EVERY = "*"   # queued on each (re)connect of the push: check every group


class Push:
    """The bot's long connection (lark-cli event consume): queues the chat_id of each pushed
    message, and EVERY whenever the connection is (re)established. Feishu delivers each event
    to one connected client only, so run Bobao for one app on one Mac."""

    def __init__(self):
        self.queue, self.profile = queue.Queue(), None

    def ensure(self, src):
        if src.get("profile") and src.get("profile") != self.profile:
            self.profile = src["profile"]
            threading.Thread(target=self.loop, args=(dict(src),), daemon=True).start()

    def loop(self, src):
        flags, _ = identity(src)
        while src["profile"] == self.profile:
            proc = subprocess.Popen([lark_cli(src), *flags, "event", "consume", "im.message.receive_v1", "--as", "bot"],
                                    stdin=subprocess.PIPE,   # it stops at stdin EOF, and launchd gives /dev/null
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env())
            threading.Thread(target=self.watch, args=(proc,), daemon=True).start()
            for line in proc.stdout:
                try:
                    chat_id = json.loads(line).get("chat_id")
                except ValueError:
                    continue
                if chat_id:
                    self.queue.put(chat_id)
            proc.wait()
            log(f"飞书推送断开（{proc.returncode}），10 秒后重连")
            time.sleep(10)

    def watch(self, proc):
        """lark-cli says "ready" when subscribed and "websocket: connected" when its shared
        bus daemon (re)connects; either way, check every group for what came meanwhile."""
        for line in proc.stderr:
            if "ready event_key=" in line or "websocket: connected" in line:
                log("飞书推送已连接，补查一遍")
                self.queue.put(EVERY)

    def take(self):
        ids = set()
        while not self.queue.empty():
            ids.add(self.queue.get())
        return ids


class Feishu:
    def __init__(self):
        self.state = read_json(paths.STATE, {}) or {}
        self.ids, self.ids_at = {}, 0
        self.push = Push()

    def groups(self, cfg):
        """The groups to read: those listed in sources.feishu.chats, or with a bot and no
        list, every group the bot was added to."""
        src = cfg["sources"]["feishu"]
        if src.get("chats") or not src.get("profile"):
            return list(src.get("chats") or [])
        if time.time() - self.ids_at > 3600 or not self.ids:
            self.refresh(src)
        return sorted(self.ids)

    def refresh(self, src):
        chats = lark(src, "im", "+chat-list", "--page-all").get("chats") or []
        self.ids = {c["name"]: c["chat_id"] for c in chats}
        self.ids_at = time.time()

    def pushed(self, cfg):
        """Names of groups the push reported since the last look (all of them after a reconnect)."""
        self.push.ensure(cfg["sources"]["feishu"])
        ids = self.push.take()
        if not ids:
            return set()
        names = self.groups(cfg)
        if EVERY in ids:
            return set(names)
        by_id = {i: n for n, i in self.ids.items()}
        return {by_id[i] for i in ids if by_id.get(i) in names}

    def chat_ids(self, cfg, names):
        src = cfg["sources"]["feishu"]
        if time.time() - self.ids_at > 3600 or any(n not in self.ids for n in names):
            self.refresh(src)
            for n in names:
                if n not in self.ids:
                    log(f"找不到飞书群「{n}」，请检查 config.json 里的群名，并确认"
                        + ("机器人已被拉进这个群" if src.get("profile") else "你在群里"))
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
