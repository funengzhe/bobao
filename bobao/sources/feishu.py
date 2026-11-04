"""Feishu / Lark groups, read through lark-cli. Cards come with every field and external
groups work.

Two ways in:
- as your own 飞书播报 bot (recommended; `bobao feishu login`): a self-built Feishu app
  whose bot you add to the groups to announce. It reads only those groups, needs no
  personal login, and its long connection pushes each new message, so a group is
  checked the moment something arrives. sources.feishu.profile names its lark-cli profile.
- as yourself (no profile): lark-cli logged in with `lark-cli auth login`; groups are
  checked every pollSeconds and when the notification helper sees a Feishu popup.

Every group is also checked every pollSeconds (5 minutes with a bot, else 20 seconds) and each time
the push connection comes back, since Feishu does not resend what was pushed while it was
down. The cursor (message_position) per group is kept in ~/.bobao/state.json, so nothing
is read twice and nothing new is skipped, however many arrive at once.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time

from .. import paths
from ..config import read_json
from ..events import Event, parse_card
from ..system import NO_WINDOW, WINDOWS
from ..log import log

HOME = os.path.expanduser("~")


# Where npm and the installers put lark-cli. The background process starts at login and may
# have an older PATH than the terminal it was set up in, so it looks in these places too.
APPDATA = os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
LARK_PLACES = ([os.path.join(APPDATA, "npm", "lark-cli.cmd"), os.path.join(HOME, "lark-cli-home", "bin", "lark-cli.cmd")]
               if WINDOWS else [f"{HOME}/.local/bin/lark-cli", "/opt/homebrew/bin/lark-cli", "/usr/local/bin/lark-cli"])
NODE_PLACES = ([os.path.join(APPDATA, "npm"), os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs")]
               if WINDOWS else [f"{HOME}/.local/node/current/bin", "/opt/homebrew/bin", "/usr/local/bin"])


def lark_cli(cfg):
    """The lark-cli to run: the one remembered at setup (sources.feishu.larkCli), else PATH,
    else where npm puts it."""
    if cfg.get("larkCli") and os.path.exists(cfg["larkCli"]):
        return cfg["larkCli"]
    return shutil.which("lark-cli") or next((p for p in LARK_PLACES if os.path.exists(p)), "lark-cli")


def found(cli):
    return bool(shutil.which(cli) or os.path.exists(cli))


def env():
    return dict(os.environ, PATH=os.pathsep.join(NODE_PLACES + [os.environ.get("PATH", "/usr/bin:/bin")]))


def identity(src):
    """lark-cli flags and --as for a source: its bot when it names a profile, else the user."""
    profile = src.get("profile")
    return (["--profile", profile] if profile else []), ("bot" if profile else "user")


def poll_seconds(src):
    return src.get("pollSeconds") or (300 if src.get("profile") else 20)   # a bot gets pushes; you are polled


def lark(src, *args, stdin=None):
    flags, who = identity(src)
    out = subprocess.run([lark_cli(src), *flags, *args, "--as", who], input=stdin, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env(), timeout=60, creationflags=NO_WINDOW)
    try:
        data = json.loads(out.stdout)
    except ValueError:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300])
    if not data.get("ok"):
        raise RuntimeError(json.dumps(data.get("error"), ensure_ascii=False)[:300])
    return data["data"]


def readable(content, me=""):
    """Mentions as people write them: @_all -> @所有人, <at ...>名字</at> -> @名字, and a
    mention of you also as "@你", so the rules for being mentioned fire."""
    content = content.replace("@_all", "@所有人")
    content = re.sub(r"<at[^>]*>([^<]*)</at>", r"@\1", content)
    if me and f"@{me}" in content:
        content = content.replace(f"@{me}", f"@{me}（@你）")
    return content


def to_event(chat, m, me=""):
    title, fields, plain = parse_card(readable(str(m.get("content") or ""), me))
    sender = (m.get("sender") or {}).get("sender_type")
    try:
        sent = time.mktime(time.strptime(m.get("create_time", ""), "%Y-%m-%d %H:%M"))
    except (ValueError, TypeError):
        sent = None
    return Event("feishu", chat, title, plain, fields, bot=None if not sender else sender == "app", time=sent)


# lark-cli's errors when your own login has run out (about 7 days unused) or was revoked
LOGIN_GONE = re.compile(r"auth login|not logged|no logged-in|unauthori[sz]ed|token.*(expired|invalid)|"
                        r"refresh.*(expired|invalid)|授权|登录|99991663|99991668|99991677|20026|20037", re.I)

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
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                    errors="replace", env=env(), creationflags=NO_WINDOW)
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
        self.me, self.me_at = "", 0   # your Feishu name, when reading as yourself
        self.login_expired = False

    def my_name(self, src):
        if not self.me and time.time() - self.me_at > 600:   # retried: you may log in after Bobao starts
            self.me_at = time.time()
            if not src.get("profile"):
                try:
                    out = subprocess.run([lark_cli(src), "auth", "status"], capture_output=True, text=True,
                                         encoding="utf-8", env=env(), timeout=30, creationflags=NO_WINDOW)
                    self.me = json.loads(out.stdout)["identities"]["user"].get("userName") or ""
                except Exception:
                    pass
        return self.me

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
                if not src.get("profile") and LOGIN_GONE.search(str(e)):
                    self.login_expired = True
                continue
            self.login_expired = False
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
                ev = to_event(name, m, self.my_name(src))
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


# ---- connecting as yourself, in one go ----------------------------------------------

SCOPES = ["im:chat:read", "im:message:readonly", "im:message.group_msg:get_as_user"]   # read-only


def status(src):
    r = subprocess.run([lark_cli(src), "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env(), timeout=60, creationflags=NO_WINDOW)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}


def logged_in(st):
    user = (st.get("identities") or {}).get("user") or {}
    return user.get("status") in ("ready", "needs_refresh") and set(SCOPES) <= set((user.get("scope") or "").split())


def wait_for_link(args, src, say, step):
    """Runs a lark-cli command that prints a link and then waits for the user to finish in the
    browser. Opens the link once and keeps waiting on it: starting again would void it."""
    from ..system import open_url
    proc = subprocess.Popen([lark_cli(src), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env=env(), creationflags=NO_WINDOW)
    shown, tail = False, []
    for line in proc.stdout:
        tail = (tail + [line.strip()])[-5:]
        m = re.search(r"https://\S+", line)
        if m and not shown:
            shown = True
            say(f"{step}：在浏览器里打开了这个页面，请在里面点「同意」（链接只能用一次，10 分钟内有效）：\n  {m.group(0)}")
            open_url(m.group(0))
    return proc.wait() == 0, " ".join(tail)


def connect(src, say=print):
    """Feishu as yourself: makes the app if there is none, then asks for the three read-only
    permissions; two pages to agree to, one after the other, nothing to type. What is
    already done is skipped, so running it again is safe once a page has been agreed to."""
    st = status(src)
    if not st.get("appId"):
        ok, why = wait_for_link(["config", "init", "--new", "--brand", "feishu", "--lang", "zh"], src, say,
                                "第 1 步，建一个只属于你的飞书应用")
        if not ok:
            raise SystemExit("飞书应用没有建好：" + why[:300])
        st = status(src)
    if logged_in(st):
        say("飞书已经授权过了，不用再点")
        return st
    r = subprocess.run([lark_cli(src), "auth", "login", "--scope", " ".join(SCOPES), "--no-wait", "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env(), timeout=60,
                       creationflags=NO_WINDOW)
    try:
        flow = json.loads(r.stdout)
    except ValueError:
        raise SystemExit("飞书授权没有发起：" + (r.stderr or r.stdout).strip()[:300])
    flow = flow.get("data", flow)
    url = next((v for k, v in flow.items() if "verification" in k and str(v).startswith("http")), "")
    code = flow.get("device_code", "")
    if not url or not code:
        raise SystemExit("飞书授权没有发起：" + (r.stderr or r.stdout).strip()[:300])
    from ..system import open_url
    say(f"第 2 步，允许 Bobao 读你的群消息（只读）：在浏览器里打开了这个页面，请点「授权」（链接只能用一次，10 分钟内有效）：\n  {url}")
    open_url(url)
    done = subprocess.run([lark_cli(src), "auth", "login", "--device-code", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env(), timeout=900, creationflags=NO_WINDOW)
    st = status(src)
    if not logged_in(st):
        raise SystemExit("还没有授权成功：" + (done.stderr or done.stdout).strip()[:300] +
                         "\n用户还没点的话，等他点完再看 lark-cli auth status；过期了才重新运行 bobao feishu connect")
    return st
