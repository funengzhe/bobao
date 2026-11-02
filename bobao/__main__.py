"""Bobao 定制播报 — the messages you care about, read aloud in a voice you like, in your words.

  bobao init                      set up: which reminders, where messages come from, how to call you
  bobao init --scenes work,life --sources notifications,remind --apps lark,wechat --name 你
                                  the same without questions (for scripts and agents)
  bobao install [--quiet]         start at login and play the install greeting
  bobao uninstall                 stop for good
  bobao status                    is it running, what was said lately
  bobao run                       run in the foreground

  bobao remind add 18:00 "下班啦" [--days 工作日] | list | remove N | test N [--play]
                                  timed reminders
  bobao notifications apps        apps that showed popups lately, and which are read
  bobao feishu login --app cli_xxx
                                  connect your 飞书播报 bot; the App Secret is read from
                                  stdin (pbpaste | bobao feishu login ...) or asked hidden
  bobao feishu groups             the groups the bot was added to
  bobao agent install claude|codex
                                  announce when Claude Code / Codex finish or wait for you
  bobao github add owner/repo | remove owner/repo | list
                                  announce new stars, forks and issues of your repos

  bobao clip make "欢迎来我家玩" [--voice 安然] [--name 欢迎] [--yes]
                                  a line in any voice, saved to share (mp3 + mp4 on the Desktop)
  bobao clip list | play 名字 | remove 名字
  bobao shout on [--voice 安然 --budget 2] | off | link
                                  the 喊话 page: friends on your Wi-Fi scan, type, this Mac says it

  bobao voices [--all]            recommended voices (--all: every RooYun voice, yours too)
  bobao rooyun login              connect your RooYun account
  bobao voice use 小柚             pick a voice, record your sentences with it, hear it introduce itself
  bobao voice plan                every sentence your setup can say, and what is unrecorded
  bobao voice quote               price of recording what is missing
  bobao voice record [--yes]      record it (asks first, shows the price)
  bobao gallery                   the listening page, served locally
  bobao review                    listen to your recordings, mark pieces to re-record

  bobao test "<title>" [-f 金额=$19.9 ...] [--channel 群名] [--source notifications] [--play]
                                  what a message would be classified and said as
  bobao replay [--chat 群名] [--limit 30]
                                  run a Feishu group's recent messages through the rules
  bobao send "<title>" [-f k=v ...] [--type 收款 --platform X]
                                  post a test message to the local webhook
  bobao packs                     list scenes, styles and rule packs
  bobao sounds                    (re)make the sound effects
  bobao export [file.zip]         settings + recordings in one file, to set up another Mac
  bobao import file.zip           take them over (no secrets inside: log in again there)
"""

import argparse
import getpass
import json
import os
import random
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from . import clips, compose, config, daemon, paths, sounds
from .events import Event


def fields_arg(pairs):
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        out[k] = v
    return out


def voice_label(v, cfg):
    if cfg["engine"] != "rooyun":
        return "电脑自带的声音"
    named = next((c["name"] for c in catalog() if c["id"] == v["voice"]), v["voice"])
    return named + (f" · {v['emotion']}" if v.get("emotion") else "")


def cmd_test(a):
    cfg = config.load()
    ev = Event(a.source, a.channel or "", a.title, a.text or "", fields_arg(a.field), bot=True,
               type=a.type, platform=a.platform)
    utt, why = daemon.decide(ev, cfg, dry=True)
    if not utt:
        print(f"不播：{why}")
        return
    m = utt["match"]
    print(f"类型：{m.type}  平台：{m.platform or '—'}  规则：{'#' + str(m.index + 1) if m.index >= 0 else ('兜底' if m.index == -2 else '来源指定')}")
    print(f"音效：{utt['sound'] or '—'}")
    for v, t in utt["segments"]:
        print(f"播报（{voice_label(v, cfg)}）：{t}")
    if cfg["engine"] == "rooyun":
        print("录音：" + ("齐全" if clips.for_segments(utt["segments"], clips.load()) else "缺（运行 bobao voice record）"))
    if a.play:
        from .speaker import play
        play(utt, cfg)


def cmd_replay(a):
    from .sources.feishu import Feishu
    cfg = config.load()
    chats = [a.chat] if a.chat else cfg["sources"]["feishu"].get("chats", [])
    index, rnd = clips.load(), random.Random(1)
    fs = Feishu()
    for chat in chats:
        print(f"== {chat}")
        for m, ev in fs.recent(cfg, chat, a.limit):
            if cfg["sources"]["feishu"].get("botsOnly", True) and ev.bot is False:
                said = "（不播：有人打字）"
            else:
                utt, why = daemon.decide(ev, cfg, dry=True, rnd=rnd)
                if utt:
                    ok = cfg["engine"] != "rooyun" or clips.for_segments(utt["segments"], index)
                    said = utt["text"] + ("" if ok else "  ← 缺录音")
                else:
                    said = f"（不播：{why}）"
            print(f"{m.get('create_time', '')}  {ev.title[:40]}  →  {said}")


def cmd_send(a):
    cfg = config.load()
    port = cfg["sources"]["webhook"].get("port", 8766)
    body = {"title": a.title, "fields": fields_arg(a.field), "dry": a.dry}
    for k in ("type", "platform", "channel"):
        if getattr(a, k):
            body[k] = getattr(a, k)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/notify", json.dumps(body).encode(),
                                 {"content-type": "application/json"})
    if cfg["sources"]["webhook"].get("secret"):
        req.add_header("x-bobao-secret", cfg["sources"]["webhook"]["secret"])
    try:
        print(urllib.request.urlopen(req, timeout=10).read().decode())
    except OSError as e:
        sys.exit(f"连不上本机 Webhook（Bobao 在运行吗？bobao status）：{e}")


def cmd_packs(a):
    for kind, label in (("scenes", "场景"), ("styles", "风格包"), ("rules", "规则包")):
        print(label)
        for name, p in config.list_packs(kind).items():
            print(f"  {name:10} {p.get('name', '')}：{p.get('description', '')}")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def catalog():
    return config.read_json(os.path.join(ROOT, "packs", "voices.json"), {"voices": []})["voices"]


def cmd_voices(a):
    if not a.all:
        print("推荐音色（试听：https://funengzhe.github.io/bobao/ ，选好后 bobao voice use 名字）")
        for v in catalog():
            print(f"  {v['name']:4} {v['label']:10} {v['gender']}·{v['age']} {'、'.join(v['tags']):12} {v['id']}")
        print("RooYun（如云）里的全部音色（含你自己克隆的）：bobao voices --all")
        return
    from .rooyun import Client
    cfg = config.load()
    for v in Client(cfg["rooyun"]["base"]).voices():
        print(f"{v['voiceId']:32} {v['name']}  {'（你的音色）' if v.get('kind') == 'user' else ''}")


def play_files(*files):
    for f in files:
        if f and os.path.exists(f):
            subprocess.run(["/usr/bin/afplay", f])


def cmd_rooyun(a):
    from . import rooyun
    cfg = config.load()
    if a.action == "login":
        rooyun.login(cfg["rooyun"]["base"])
    else:
        me = rooyun.Client(cfg["rooyun"]["base"]).me()
        print(json.dumps({k: me.get(k) for k in ("userId", "scopes", "expiresAt")}, ensure_ascii=False))


INTRO_PENDING = "intro-pending"   # the voice chosen with `voice use`, introduced once recorded


def pending_voice():
    try:
        return open(os.path.join(paths.HOME, INTRO_PENDING), encoding="utf-8").read().strip() or None
    except FileNotFoundError:
        return None


def switch_voice(voice_id, picked):
    """The chosen voice is recorded: use it from now on, and let it introduce itself."""
    user = config.read_json(paths.CONFIG, {}) or {}
    user["engine"] = "rooyun"
    user["voices"] = {"default": {"voice": voice_id}}
    config.save_user(user)
    os.remove(os.path.join(paths.HOME, INTRO_PENDING))
    name = picked["name"] if picked else voice_id
    print(f"已换成 {name}。")
    if picked:
        print(f"{name}：我是{name}，这是我的声音，之后由我来为你播报。")
        play_files(os.path.join(ROOT, "docs", picked["intro"]))


def cmd_voice(a):
    if a.action == "use" and a.cancel:
        if os.path.exists(os.path.join(paths.HOME, INTRO_PENDING)):
            os.remove(os.path.join(paths.HOME, INTRO_PENDING))
        print("不换了，声音保持原样")
        return
    if a.action == "use":
        if not a.name:
            raise SystemExit("用法：bobao voice use 名字（或 RooYun 音色 id）；推荐音色见 bobao voices")
        picked = next((v for v in catalog() if a.name in (v["name"], v["id"])), None)
        voice_id = picked["id"] if picked else a.name
        with open(os.path.join(paths.HOME, INTRO_PENDING), "w", encoding="utf-8") as f:
            f.write(voice_id)
        print(f"选了 {picked['name'] if picked else voice_id}。要先用它把你的播报内容生成一遍，生成完才换过去：")
        a.action = "record" if a.yes else "quote"
    pending = pending_voice()
    picked = next((v for v in catalog() if v["id"] == pending), None)
    user = config.read_json(paths.CONFIG, {}) or {}
    if pending:   # plan and record for the chosen voice; the setup switches once it is recorded
        user = dict(user, engine="rooyun", voices={"default": {"voice": pending}})
    cfg = config.load(user)
    p = compose.plan(cfg)
    todo = clips.missing(p, clips.load())
    total = sum(len(e["phrases"]) for e in p.values())
    if a.action == "plan":
        for vkey, e in p.items():
            print(f"== {vkey}（{len(e['phrases'])} 句{' + 数字' if e['numbers'] else ''}）")
            for t in e["phrases"]:
                print(("  ✓ " if t not in todo.get(vkey, []) else "  · ") + t)
        numbers = sum(1 for e in p.values() if e["numbers"])
        print(f"\n共 {total} 句" + (f"，外加 {numbers} 个音色各一套数字" if numbers else "") + f"；还没录 {sum(len(v) for v in todo.values())} 段")
        return
    if not todo:
        print("全部都录好了")
        if a.action == "record" and pending:
            switch_voice(pending, picked)
        return
    from . import rooyun
    client = rooyun.Client(cfg["rooyun"]["base"])
    meta = {v["voiceId"]: v for v in client.voices()}
    jobs = rooyun.jobs_for(todo, client, cfg, meta)
    price, available = rooyun.quote(client, jobs)
    minutes = round(len(jobs) * rooyun.SUBMIT_GAP / 60)
    print(f"要录 {len(jobs)} 句，约 {price} 积分，你的可用积分 {round(available, 2)}（RooYun 每分钟最多提交 10 句，约 {minutes} 分钟）")
    if a.action == "quote":
        print("确认后：bobao voice record --yes" + ("；不换了：bobao voice use --cancel" if pending else ""))
        return
    if price > available:
        sys.exit("积分不够，请先到 RooYun（如云）充值")
    if not a.yes and input("开始录吗？[y/N] ").strip().lower() not in ("y", "yes", "是"):
        print("没有录")
        return
    done, failed = rooyun.record(client, jobs)
    print(f"录好 {done} 句" + (f"，{failed} 句没录成（重跑同一条命令补录）" if failed else ""))
    if pending and not failed:
        switch_voice(pending, picked)


def cmd_agent(a):
    from . import agents
    if a.action == "install":
        if a.which not in ("claude", "codex"):
            raise SystemExit("用法：bobao agent install claude 或 codex")
        print(agents.install(a.which))
        print("记得 bobao install 让后台在运行；试一下：bobao send 智能体完成 --channel \"Claude Code\"")
        return
    agents.hook([a.action, a.which or ""] + list(a.rest))   # called by the hooks themselves


def cmd_github(a):
    user = config.read_json(paths.CONFIG, {}) or {}
    gh = user.setdefault("sources", {}).setdefault("github", {})
    repos = gh.setdefault("repos", [])
    if a.action in ("add", "remove"):
        repo = (a.repo or "").replace("https://github.com/", "").strip("/")
        if repo.count("/") != 1:
            raise SystemExit("用法：bobao github add 用户名/仓库名")
        if a.action == "add" and repo not in repos:
            repos.append(repo)
        if a.action == "remove" and repo in repos:
            repos.remove(repo)
        gh["enabled"] = bool(repos)
        config.save_user(user)
    print("在看的仓库：" + ("、".join(repos) or "还没有") + "（每 10 分钟看一次，有新的 star、fork、Issue 就播报）")


def cmd_clip(a):
    from . import share
    if a.action == "make":
        if not a.text:
            raise SystemExit('用法：bobao clip make "想说的话" --voice 安然')
        share.make(a.text, a.voice, a.name, a.yes, catalog())
    elif a.action == "list":
        items = share.load()
        for c in items:
            print(f"  {c['name']:12} {c.get('voiceName', ''):6} {c['text']}" + ("" if c.get("file") else "（还没生成）"))
        print("" if items else '还没有。做一句：bobao clip make "欢迎来我家玩" --voice 安然')
    elif a.action in ("play", "remove"):
        c = share.find(a.text or "")
        if not c:
            raise SystemExit(f"没有叫「{a.text}」的，看看 bobao clip list")
        if a.action == "play":
            play_files(c.get("file"))
        else:
            share.remove(c["name"])
            print(f"删掉了「{c['name']}」（桌面上的副本留着）")


def cmd_shout(a):
    from . import shout
    if a.action == "off":
        shout.turn_off()
        print("喊话页关了")
        return
    voice = a.voice and next((v["id"] for v in catalog() if a.voice in (v["name"], v["id"])), a.voice)
    sh = shout.turn_on(voice, a.budget) if a.action == "on" else config.load()["sources"]["shout"]
    if not sh.get("enabled"):
        raise SystemExit("喊话页没开：bobao shout on")
    urls = shout.links(sh.get("port", 8769), sh["token"])
    print("喊话页（手机和这台电脑连同一个 Wi-Fi）：\n  " + "\n  ".join(urls))
    if sh.get("voice") and sh.get("budget"):
        named = next((v["name"] for v in catalog() if v["id"] == sh["voice"]), sh["voice"])
        print(f"打的字用 {named} 念，每天最多花 {sh['budget']} 积分，超了改用电脑声音")
    else:
        print("打的字用电脑自带的声音念，免费；你做好的句子（bobao clip）是页面上的按钮")
    print("后台要在运行（bobao install）；第一次打开时 macOS 可能问是否允许 python3 接受连接，点允许")
    if not a.no_open:
        subprocess.run(["/usr/bin/open", shout.qr_page(urls)])


def cmd_sounds(a):
    print("已生成音效：" + "、".join(sounds.make_all()) + f"（在 {paths.SOUNDS}）")


def cmd_status(a):
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{AGENT}"], capture_output=True, text=True)
    print("后台：" + ("运行中" if "state = running" in r.stdout else "没有运行（bobao install 安装）"))
    try:
        with open(paths.LOG, encoding="utf-8") as f:
            print("".join(f.readlines()[-15:]))
    except FileNotFoundError:
        pass


# ---- setup ------------------------------------------------------------------

AGENT, HELPER = "io.bobao.agent", "io.bobao.notify"
# Popup sources, by a part of the app id (matched ignoring case)
APPS = [("飞书", "lark"), ("企业微信", "wework"), ("钉钉", "dingtalk"), ("微信", "wechat"), ("日历", "ical"),
        ("邮件", "com.apple.mail"), ("提醒事项", "reminders"), ("Slack", "slack")]
SCENE_APPS = {"work": ["lark", "wework", "dingtalk", "ical"], "life": ["wechat", "com.apple.mail", "ical", "reminders"],
              "live": ["wechat"], "business": [], "dev": ["com.apple.mail"], "blank": []}
SOURCES = ("feishu", "webhook", "notifications", "remind")


def ask(q, default=""):
    v = input(f"{q}" + (f" [{default}]" if default else "") + "：").strip()
    return v or default


def choose(q, options, default=1):
    for i, (label, _) in enumerate(options, 1):
        print(f"  {i}. {label}")
    v = ask(q, str(default))
    picks = [int(x) for x in v.replace("，", ",").replace(" ", ",").split(",") if x.strip().isdigit()]
    return [options[i - 1][1] for i in picks if 0 < i <= len(options)]


def split(v):
    return [x.strip() for x in (v or "").replace("，", ",").split(",") if x.strip()]


def app_ids(names):
    """--apps takes 飞书, 企业微信… or a part of any app id."""
    known = dict(APPS)
    return [known.get(n, n) for n in names]


def apply_sources(user, picked, apps=None, chats=None, before=()):
    src = user.setdefault("sources", {})
    for name in ("feishu", "webhook", "notifications"):
        src[name] = dict(src.get(name, {}), enabled=name in picked)
    if "notifications" in picked:
        if apps is None:   # keep what was chosen, add what newly picked scenes read
            had = src["notifications"].get("apps", [])
            added = [sc for sc in config.scene_names(user) if not had or sc not in before]
            apps = had + [x for sc in added for x in SCENE_APPS.get(sc, [])]
        src["notifications"]["apps"] = list(dict.fromkeys(apps)) or ["wechat"]
    if chats is not None:
        src["feishu"]["chats"] = chats
    if "remind" not in picked:
        user["reminders"] = []
    elif user.get("reminders") == []:
        user.pop("reminders")   # back to the scenes' reminders


def enabled_sources(user):
    """What a saved setup uses now, in init's terms (empty for a new one)."""
    if "sources" not in user:
        return []
    on = [n for n in ("notifications", "feishu", "webhook") if user["sources"].get(n, {}).get("enabled")]
    return on + ([] if user.get("reminders") == [] else ["remind"])


def summary(user, picked):
    cfg = config.load()
    names = [config.list_packs("scenes").get(n, {}).get("name", n) for n in config.scene_names(user)]
    voice = "RooYun · " + config.voice_for(cfg, "提醒")["voice"] if cfg["engine"] == "rooyun" else "电脑自带"
    print(f"已保存 {paths.CONFIG}：场景 {'、'.join(names) or '无'}，风格 {cfg['styleName']}，称呼 {cfg['称呼']}，"
          f"声音 {voice}，来源 {'、'.join(picked)}" + (f"，定时提醒 {len(cfg['reminders'])} 条" if cfg["reminders"] else ""))
    if "notifications" in picked:
        names = {k: n for n, k in APPS}
        apps = cfg["sources"]["notifications"].get("apps", [])
        print("读这些 App 的弹窗：" + "、".join(names.get(x, x) for x in apps) + "（改：--apps 飞书,微信）")


def init_quiet(a):
    """bobao init with flags: no questions; what is not given keeps its value or the scenes'."""
    user = config.read_json(paths.CONFIG, {}) or {}
    scenes, styles = config.list_packs("scenes"), config.list_packs("styles")
    titles = {p["name"]: k for k, p in scenes.items()}
    wanted = split(a.scenes or a.scene)
    for n in wanted:
        if n not in scenes and n not in titles:
            choices = "、".join(f"{k}（{p['name']}）" for k, p in scenes.items())
            raise SystemExit(f"没有这个场景：{n}（可选：{choices}）")
    if a.style and a.style not in styles:
        raise SystemExit(f"没有这个风格：{a.style}（可选：{'、'.join(styles)}）")
    had, before = enabled_sources(user), config.scene_names(user)
    if wanted:
        user["scenes"] = [titles.get(n, n) for n in wanted]
        user.pop("scene", None)
        if user.get("reminders"):   # the user's own list: add what the new scenes bring
            new = config.with_scene({"scenes": user["scenes"]}).get("reminders", [])
            user["reminders"] += [r for r in new if r not in user["reminders"]]
        else:
            user.pop("reminders", None)
    if a.style:
        user["style"] = a.style
    if a.name:
        user["称呼"] = a.name
    if a.engine:
        user["engine"] = a.engine
    if a.rule_packs:
        user["rulePacks"] = split(a.rule_packs)
    first = scenes.get((config.scene_names(user) or [""])[0], {})
    picked = split(a.sources) or had or first.get("suggestSources", ["notifications"])
    bad = [x for x in picked if x not in SOURCES]
    if bad:
        raise SystemExit(f"没有这个来源：{'、'.join(bad)}（可选：{'、'.join(SOURCES)}）")
    apply_sources(user, picked, app_ids(split(a.apps)) if a.apps else None, split(a.chats) if a.chats else None, before)
    config.save_user(user)
    sounds.make_all()
    summary(user, picked)


def cmd_init(a):
    if any(v is not None for v in (a.scene, a.scenes, a.style, a.name, a.engine, a.sources, a.rule_packs, a.chats, a.apps)) or a.yes:
        return init_quiet(a)
    user = config.read_json(paths.CONFIG, {}) or {}
    print("Bobao 定制播报 · 设置（直接回车用括号里的默认值）\n")
    scenes = config.list_packs("scenes")
    print("1) 你想听哪些提醒？可以多选，用逗号隔开（之后随时能改、能加）")
    user["scenes"] = choose("选择", [(f"{p['name']}：{p['who']}", k) for k, p in scenes.items()], "1") or ["blank"]
    user.pop("scene", None)
    print("2) 这些消息从哪来？可以多选")
    first = scenes.get(user["scenes"][0], {})
    picked = choose("选择", [("电脑上的弹窗：飞书、企业微信、钉钉、微信、日历、邮件…", "notifications"),
                             ("飞书群里的机器人通知（要建一个「飞书播报」应用，见 AGENTS.md）", "feishu"),
                             ("你自己的系统推过来（Webhook）", "webhook"),
                             ("定时提醒（例如工作日六点提醒下班）", "remind")],
                    ",".join(str(i) for i, s in enumerate(("notifications", "feishu", "webhook", "remind"), 1)
                             if s in first.get("suggestSources", ["notifications"])))
    apps = None
    if "notifications" in picked:
        default = [x for sc in user["scenes"] for x in SCENE_APPS.get(sc, [])]
        apps = choose("  读哪些 App 的弹窗", APPS, ",".join(str(i) for i, (_, k) in enumerate(APPS, 1) if k in default) or "1")
    user["称呼"] = ask("3) 怎么称呼你（你、老板、名字…）", user.get("称呼") or first.get("称呼") or "你")
    apply_sources(user, picked, apps)
    config.save_user(user)
    sounds.make_all()
    summary(user, picked)
    print("\n下一步：bobao install 装好（会播一句安装提示）。想换好听的声音：打开 https://funengzhe.github.io/bobao/ 挑一个，"
          "再 bobao voice use 名字。")


DAYS = {"每天": None, "工作日": [1, 2, 3, 4, 5], "周末": [6, 7]}


def parse_days(v):
    if not v or v in DAYS:
        return DAYS.get(v or "每天")
    out = []
    for part in v.replace("，", ",").split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    if not out or any(d < 1 or d > 7 for d in out):
        raise SystemExit("--days 写成 1-5、6,7、工作日、周末 或 每天（1 是周一）")
    return out


def cmd_remind(a):
    user = config.read_json(paths.CONFIG, {}) or {}
    current = config.load()["reminders"]
    if a.action == "list":
        if not current:
            print("还没有定时提醒。添加：bobao remind add 18:00 \"下班啦\" --days 工作日")
        for i, r in enumerate(current, 1):
            days = r.get("days")
            when = "每天" if not days or sorted(days) == list(range(1, 8)) else next((k for k, d in DAYS.items() if d == days), "周" + "、".join(map(str, days)))
            print(f"  {i}. {when} {r['at']}  {r['say']}")
        return
    if a.action == "test":
        n = int(a.at or 0)
        if not 0 < n <= len(current):
            raise SystemExit("用法：bobao remind test 编号 [--play]（编号见 bobao remind list）")
        cfg = config.load()
        utt = daemon.reminder_utterance(cfg, current[n - 1])
        for v, t in utt["segments"]:
            print(f"播报（{voice_label(v, cfg)}）：{t}")
        if cfg["engine"] == "rooyun":
            print("录音：" + ("齐全" if clips.for_segments(utt["segments"], clips.load()) else "缺（运行 bobao voice record）"))
        if a.play:
            from .speaker import play
            play(utt, cfg)
        return
    if a.action == "add":
        if not a.at or not a.say:
            raise SystemExit('用法：bobao remind add 18:00 "要说的话" [--days 工作日]')
        h, _, m = a.at.partition(":")
        if not (h.isdigit() and m.isdigit() and int(h) < 24 and int(m) < 60):
            raise SystemExit("时间写成 HH:MM，比如 09:30")
        r = {"at": f"{int(h):02d}:{int(m):02d}", "say": a.say}
        if parse_days(a.days):
            r["days"] = parse_days(a.days)
        current.append(r)
    else:
        n = int(a.at or 0)
        if not 0 < n <= len(current):
            raise SystemExit("用法：bobao remind remove 编号（编号见 bobao remind list）")
        current.pop(n - 1)
    user["reminders"] = current   # from now on the user's own list
    config.save_user(user)
    print(f"已保存，共 {len(current)} 条定时提醒。" + ("后台在运行的话会自动生效；改了说法用 bobao voice record 补录。"
                                                 if config.load()["engine"] == "rooyun" else ""))


def cmd_notifications(a):
    exe = os.path.join(paths.APP, "Bobao 通知.app", "Contents", "MacOS", "bobao-notify")
    if not os.path.exists(exe):
        raise SystemExit("还没装系统通知助手：先 bobao init 选「电脑上的弹窗」，再 bobao install")
    r = subprocess.run([exe, "--dump", "300"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("读不到通知：请在 系统设置 → 隐私与安全性 → 完全磁盘访问权限 里打开「Bobao 通知」")
    counts = {}
    for line in r.stdout.splitlines():
        if line.startswith("["):
            app = line[1:line.index("]")]
            counts[app] = counts.get(app, 0) + 1
    watched = config.load()["sources"]["notifications"].get("apps", [])
    print("最近弹过通知的 App（次数）：")
    for app, n in sorted(counts.items(), key=lambda x: -x[1]):
        on = any(w.lower() in app.lower() for w in watched)
        print(f"  {'✓' if on else ' '} {app:40} {n}")
    print(f"✓ = 正在读（{', '.join(watched) or '无'}）。要加：bobao init --sources notifications --apps 原有,新的")


def cmd_feishu(a):
    from .sources import feishu
    user = config.read_json(paths.CONFIG, {}) or {}
    src = dict((user.get("sources") or {}).get("feishu") or {})
    if a.action == "login":
        if not a.app:
            raise SystemExit("用 --app 给出应用的 App ID（cli_ 开头，在开放平台「凭证与基础信息」里）")
        secret = sys.stdin.read().strip() if not sys.stdin.isatty() else getpass.getpass("粘贴 App Secret（不会显示）：").strip()
        if not secret:
            raise SystemExit("没有读到 App Secret。复制后运行：pbpaste | bobao feishu login --app " + a.app)
        cli = feishu.lark_cli(src)
        if not shutil.which(cli) and not os.path.exists(cli):
            raise SystemExit("没有找到 lark-cli。先安装：npm install -g @larksuite/cli")
        r = subprocess.run([cli, "config", "init", "--name", a.profile, "--app-id", a.app, "--app-secret-stdin"],
                           input=secret, capture_output=True, text=True, env=feishu.env())
        if r.returncode:
            raise SystemExit("lark-cli 没有接受这组 App ID / Secret：" + (r.stderr or r.stdout).strip()[:300])
        src.update(enabled=True, profile=a.profile, app=a.app)
        user.setdefault("sources", {})["feishu"] = src
        config.save_user(user)
        print(f"已连接飞书应用 {a.app}（lark-cli 配置「{a.profile}」），Secret 只存在 lark-cli 里，不在 Bobao 的设置中。")
    if not src.get("profile"):
        raise SystemExit("还没有连接飞书机器人：bobao feishu login --app cli_xxx")
    try:
        chats = feishu.lark(src, "im", "+chat-list", "--page-all").get("chats") or []
    except Exception as e:
        raise SystemExit(f"机器人读不到群：{e}\n检查开放平台里是否开通了「查看群信息」等权限，并已发布版本。")
    if not chats:
        print("机器人还不在任何群里：在飞书里打开要播报的群 → 设置 → 群机器人 → 添加机器人，搜索你的应用。")
        return
    listed = src.get("chats") or []
    print("机器人所在的群（" + ("只播 config 里列出的" if listed else "全部会播") + "）：")
    for c in chats:
        mark = "" if not listed or c["name"] in listed else "（不播）"
        print(f"  {c['name']}{'  · 外部群' if c.get('external') else ''}{mark}")


EXPORT_SKIP = {"state.json", "bobao.log", "notify.log", "recording.json", "notifications.jsonl", "last.wav", "pending.txt"}


def cmd_export(a):
    """Settings, recordings, sounds and the user's own packs; no state, logs or secrets."""
    out = os.path.abspath(a.file or f"bobao-{os.environ.get('USER', 'me')}.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(paths.HOME):
            rel = os.path.relpath(root, paths.HOME)
            if rel.split(os.sep)[0] in ("app",):
                dirs[:] = []
                continue
            for f in files:
                if (rel == "." and f in EXPORT_SKIP) or f.endswith((".tmp", ".DS_Store")):
                    continue
                z.write(os.path.join(root, f), os.path.normpath(os.path.join(rel, f)))
                n += 1
    secret = ((config.read_json(paths.CONFIG, {}) or {}).get("sources", {}).get("webhook", {}) or {}).get("secret")
    print(f"已导出 {n} 个文件到 {out}（{os.path.getsize(out) // 1024} KB）")
    print("里面没有飞书 App Secret 和 RooYun（如云）登录；对方导入后要自己运行一次 bobao feishu login。"
          + ("\n注意：webhook 的 secret 在设置里，会一起带过去。" if secret else ""))


def cmd_import(a):
    with zipfile.ZipFile(a.file) as z:
        names = z.namelist()
        bad = [x for x in names if x.startswith("/") or ".." in x.split("/")]
        if bad or "config.json" not in names:
            raise SystemExit("这不是 bobao export 导出的文件")
        paths.ensure()
        had = os.path.exists(paths.CONFIG)
        if had:
            shutil.copy(paths.CONFIG, paths.CONFIG + ".before-import")
        z.extractall(paths.HOME)
    cfg = config.load()
    print(f"已导入 {len(names)} 个文件到 {paths.HOME}" + ("（原来的设置备份为 config.json.before-import）" if had else ""))
    fs = cfg["sources"]["feishu"]
    if fs.get("enabled") and fs.get("app"):
        print(f"下一步：复制飞书应用 {fs['app']} 的 App Secret，运行 pbpaste | bobao feishu login --app {fs['app']}")


def plist(label, args, log):
    items = "".join(f"<string>{x}</string>" for x in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key><array>{items}</array>
  <key>WorkingDirectory</key><string>{paths.APP}</string>
  <key>EnvironmentVariables</key><dict><key>BOBAO_HOME</key><string>{paths.HOME}</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>30</integer>
  <key>StandardErrorPath</key><string>{log}</string><key>StandardOutPath</key><string>{log}</string>
</dict></plist>
"""


def load_agent(label, text):
    path = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    with open(path, "w") as f:
        f.write(text)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", path], check=True)


def cmd_install(a):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths.ensure()
    # Background agents may not read ~/Documents, so the agent runs from a copy.
    for d in ("bobao", "packs", "bin"):
        shutil.rmtree(os.path.join(paths.APP, d), ignore_errors=True)
        shutil.copytree(os.path.join(here, d), os.path.join(paths.APP, d), ignore=shutil.ignore_patterns("__pycache__"))
    if not os.listdir(paths.SOUNDS):
        sounds.make_all()
    load_agent(AGENT, plist(AGENT, ["/usr/bin/python3", "-m", "bobao", "run"], paths.LOG))
    print("后台已启动，开机自动运行。日志：" + paths.LOG)
    cfg = config.load()
    fs = cfg["sources"]["feishu"]
    # The helper reads popups: needed for system notifications, and as a nudge for Feishu read
    # as the user; a Feishu bot gets pushes instead.
    if cfg["sources"]["notifications"].get("enabled") or (fs.get("enabled") and not fs.get("profile")):
        app = os.path.join(paths.APP, "Bobao 通知.app")
        exe = os.path.join(app, "Contents", "MacOS", "bobao-notify")
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        with open(os.path.join(app, "Contents", "Info.plist"), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>CFBundleIdentifier</key>'
                    '<string>io.bobao.notify</string><key>CFBundleName</key><string>Bobao 通知</string>'
                    '<key>CFBundleExecutable</key><string>bobao-notify</string><key>LSUIElement</key><true/></dict></plist>')
        subprocess.run(["swiftc", "-O", "-o", exe, os.path.join(here, "helper", "bobao-notify.swift")], check=True)
        # A fixed designated requirement keeps the Full Disk Access grant across rebuilds.
        subprocess.run(["codesign", "-f", "-s", "-", "--identifier", "io.bobao.notify",
                        "-r=designated => identifier \"io.bobao.notify\"", app], check=True, capture_output=True)
        load_agent(HELPER, plist(HELPER, [exe], os.path.join(paths.HOME, "notify.log")))
        print(f"系统通知助手已启动。请在 系统设置 → 隐私与安全性 → 完全磁盘访问权限 里添加并打开：\n  {app}")
    if not a.quiet:   # the install greeting: a doorbell, then 小柚
        play_files(os.path.join(paths.SOUNDS, "doorbell.wav"), os.path.join(here, "assets", "welcome.mp3"))


def cmd_uninstall(a):
    for label in (AGENT, HELPER):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
        try:
            os.remove(os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist"))
        except FileNotFoundError:
            pass
    print(f"已停止并移除开机启动。设置和录音还在 {paths.HOME}，不要了可以整个删掉。")


def main(argv=None):
    p = argparse.ArgumentParser(prog="bobao", description="Bobao 定制播报", formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    sub = p.add_subparsers(dest="cmd")
    for name in ("run", "uninstall", "status", "packs", "sounds"):
        sub.add_parser(name)
    ins = sub.add_parser("install")
    ins.add_argument("--quiet", action="store_true", help="不播安装提示")
    vs = sub.add_parser("voices")
    vs.add_argument("--all", action="store_true", help="RooYun（如云）里的全部音色")
    rm = sub.add_parser("remind")
    rm.add_argument("action", choices=["add", "list", "remove", "test"])
    rm.add_argument("at", nargs="?", help="add：HH:MM；remove、test：编号")
    rm.add_argument("say", nargs="?")
    rm.add_argument("--days", help="工作日、周末、每天，或 1-5、6,7（1 是周一）")
    rm.add_argument("--play", action="store_true")
    nt = sub.add_parser("notifications")
    nt.add_argument("action", choices=["apps"])
    i = sub.add_parser("init")
    i.add_argument("--scene")
    i.add_argument("--scenes", help="场景，可多个：work,life 或 上班,生活")
    i.add_argument("--apps", help="读哪些 App 的弹窗（App id 的一部分）：lark,wechat")
    i.add_argument("--style")
    i.add_argument("--name", help="怎么称呼你")
    i.add_argument("--engine", choices=["mac", "rooyun"])
    i.add_argument("--sources", help="notifications,feishu,webhook,remind")
    i.add_argument("--rule-packs")
    i.add_argument("--chats", help="只播这些飞书群（逗号隔开）；用机器人时可不填，播它所在的全部群")
    i.add_argument("--yes", action="store_true", help="不提问，全用场景默认值")
    fe = sub.add_parser("feishu")
    fe.add_argument("action", choices=["login", "groups"])
    fe.add_argument("--app")
    fe.add_argument("--profile", default="bobao")
    ex = sub.add_parser("export")
    ex.add_argument("file", nargs="?")
    im = sub.add_parser("import")
    im.add_argument("file")
    g = sub.add_parser("gallery")
    g.add_argument("--port", type=int, default=8768)
    g.add_argument("--no-open", action="store_true")
    rv = sub.add_parser("review")
    rv.add_argument("--port", type=int, default=8767)
    rv.add_argument("--no-open", action="store_true")
    t = sub.add_parser("test")
    t.add_argument("title")
    t.add_argument("--text")
    t.add_argument("-f", "--field", action="append")
    t.add_argument("--channel")
    t.add_argument("--source", default="feishu")
    t.add_argument("--type")
    t.add_argument("--platform")
    t.add_argument("--play", action="store_true")
    r = sub.add_parser("replay")
    r.add_argument("--chat")
    r.add_argument("--limit", type=int, default=30)
    s = sub.add_parser("send")
    s.add_argument("title")
    s.add_argument("-f", "--field", action="append")
    s.add_argument("--type")
    s.add_argument("--platform")
    s.add_argument("--channel")
    s.add_argument("--dry", action="store_true")
    ag = sub.add_parser("agent")
    ag.add_argument("action", help="install，或钩子自己用的 claude / codex")
    ag.add_argument("which", nargs="?")
    ag.add_argument("rest", nargs="*")
    gh = sub.add_parser("github")
    gh.add_argument("action", choices=["add", "remove", "list"])
    gh.add_argument("repo", nargs="?")
    cl = sub.add_parser("clip")
    cl.add_argument("action", choices=["make", "list", "play", "remove"])
    cl.add_argument("text", nargs="?", help="make：要说的话；play、remove：名字")
    cl.add_argument("--voice", help="音色名字或 RooYun 音色 id")
    cl.add_argument("--name", help="起个名字，默认取前几个字")
    cl.add_argument("--yes", action="store_true")
    sh = sub.add_parser("shout")
    sh.add_argument("action", choices=["on", "off", "link"])
    sh.add_argument("--voice", help="打的字用这个 RooYun 音色念（要配 --budget）")
    sh.add_argument("--budget", type=float, help="每天最多花多少积分")
    sh.add_argument("--no-open", action="store_true")
    ry = sub.add_parser("rooyun")
    ry.add_argument("action", choices=["login", "me"])
    v = sub.add_parser("voice")
    v.add_argument("action", choices=["plan", "quote", "record", "use"])
    v.add_argument("name", nargs="?", help="use：音色名字或 RooYun（如云）音色 id")
    v.add_argument("--cancel", action="store_true", help="use：不换了")
    v.add_argument("--yes", action="store_true")
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return
    if a.cmd == "run":
        return daemon.run()
    if a.cmd == "gallery":   # the listening page in docs/, served locally
        import functools
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        docs = os.path.join(root, "docs")
        server = ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(SimpleHTTPRequestHandler, directory=docs))
        print(f"试听页面：http://127.0.0.1:{a.port}")
        if not a.no_open:
            subprocess.run(["/usr/bin/open", f"http://127.0.0.1:{a.port}"])
        return server.serve_forever()
    if a.cmd == "review":
        from . import review
        return review.serve(a.port, not a.no_open)
    {"init": cmd_init, "install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status, "packs": cmd_packs,
     "voices": cmd_voices, "sounds": cmd_sounds, "test": cmd_test, "replay": cmd_replay, "send": cmd_send,
     "rooyun": cmd_rooyun, "voice": cmd_voice, "feishu": cmd_feishu, "export": cmd_export,
     "import": cmd_import, "remind": cmd_remind, "notifications": cmd_notifications, "agent": cmd_agent,
     "github": cmd_github, "clip": cmd_clip, "shout": cmd_shout}[a.cmd](a)


if __name__ == "__main__":
    main()
