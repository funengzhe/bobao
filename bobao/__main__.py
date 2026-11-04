"""Bobao 定制播报 — the messages you care about, read aloud in a voice you like, in your words.

  bobao init                      set up: which reminders, where messages come from
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
  bobao feishu me --chats 群1,群2 [--people]
                                  read Feishu as yourself (lark-cli auth login), no bot needed
  bobao agent done | waiting [--name Cursor]
                                  any agent's hook: a task is finished / it waits for you
  bobao agent install claude|codex | setup
                                  ready-made hooks for Claude Code and Codex; setup: for any other
  bobao github add owner/repo | remove owner/repo | list
                                  announce new stars, forks and issues of your repos

  bobao clip make "欢迎来我家玩" [--voice 安然] [--name 欢迎] [--yes]
                                  a line in any voice, saved to share (mp3 + mp4 on the Desktop)
  bobao clip list | play 名字 | remove 名字
  bobao shout on [--voice 安然 --budget 2] | off | link
                                  the 喊话 page: friends on your Wi-Fi scan, type, this Mac says it

  bobao voices [--all]            recommended voices (--all: every RooYun voice, yours too)
  bobao rooyun login              connect your RooYun account
  bobao voice listen 安然          hear a recommended voice introduce itself (free)
  bobao voice use 小柚             pick a voice (or 招牌搭配), record your sentences with it
  bobao recommend                 voices for your scenes, scenes to add, fun extras
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

from . import clips, compose, config, daemon, paths, sounds, system
from .events import Event


LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 never goes through a proxy


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
        print(LOCAL.open(req, timeout=10).read().decode())
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
        system.play(f)


def cmd_rooyun(a):
    from . import rooyun
    cfg = config.load()
    if a.action == "login":
        rooyun.login(cfg["rooyun"]["base"])
    else:
        me = rooyun.Client(cfg["rooyun"]["base"]).me()
        print(json.dumps({k: me.get(k) for k in ("userId", "scopes", "expiresAt")}, ensure_ascii=False))


INTRO_PENDING = "intro-pending"   # the voice chosen with `voice use`, introduced once recorded


def recommendations():
    return config.read_json(os.path.join(ROOT, "packs", "recommend.json"), {}) or {}


def pending_voice():
    """(voices for each type, name) chosen with `voice use`, or None. The file holds a voice
    id (one voice) or JSON {"name", "voices"} (a bundle such as 招牌搭配)."""
    try:
        raw = open(os.path.join(paths.HOME, INTRO_PENDING), encoding="utf-8").read().strip()
    except FileNotFoundError:
        return None
    if not raw:
        return None
    if raw.startswith("{"):
        d = json.loads(raw)
        return d["voices"], d["name"]
    return {"default": {"voice": raw}}, raw


def switch_voice(voices, name):
    """The chosen voice is recorded: use it from now on, and let it introduce itself."""
    user = config.read_json(paths.CONFIG, {}) or {}
    user["engine"] = "rooyun"
    user["voices"] = voices
    config.save_user(user)
    os.remove(os.path.join(paths.HOME, INTRO_PENDING))
    picked = next((v for v in catalog() if v["id"] == voices["default"]["voice"]), None)
    print(f"已换成 {next((v['name'] for v in catalog() if v['id'] == name), name)}。")
    if picked:
        print(f"{picked['name']}：我是{picked['name']}，这是我的声音，之后由我来为你播报。")
        play_files(os.path.join(ROOT, "docs", picked["intro"]))


def cmd_voice(a):
    if a.action == "listen":   # a recommended voice's self-introduction, from the listening page's audio
        v = next((v for v in catalog() if a.name in (v["name"], v["id"])), None)
        if not v:
            raise SystemExit("没有这个推荐声音，看看 bobao voices")
        print(f"{v['name']}（{v['label']}）：我是{v['name']}……")
        play_files(os.path.join(ROOT, "docs", v["intro"]))
        return
    if a.action == "use" and a.cancel:
        if os.path.exists(os.path.join(paths.HOME, INTRO_PENDING)):
            os.remove(os.path.join(paths.HOME, INTRO_PENDING))
        print("不换了，声音保持原样")
        return
    if a.action == "use":
        if not a.name:
            raise SystemExit("用法：bobao voice use 名字（或 RooYun 音色 id）；推荐音色见 bobao voices")
        preset = recommendations().get("presets", {}).get(a.name)
        picked = next((v for v in catalog() if a.name in (v["name"], v["id"])), None)
        paths.ensure()
        with open(os.path.join(paths.HOME, INTRO_PENDING), "w", encoding="utf-8") as f:
            f.write(json.dumps({"name": a.name, "voices": preset["voices"]}, ensure_ascii=False) if preset
                    else (picked["id"] if picked else a.name))
        label = a.name if preset else (picked["name"] if picked else a.name)
        print(f"选了 {label}。要先用它把你的播报内容生成一遍，生成完才换过去：")
        a.action = "record" if a.yes else "quote"
    pending = pending_voice()
    user = config.read_json(paths.CONFIG, {}) or {}
    if pending:   # plan and record for the chosen voice; the setup switches once it is recorded
        user = dict(user, engine="rooyun", voices=pending[0])
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
            switch_voice(*pending)
        return
    if a.action == "quote":   # what will be recorded comes before what it costs
        from .numbers import vocabulary
        words = set(vocabulary())
        print("要录的句子：")
        for vkey, texts in todo.items():
            name = voice_label(p[vkey]["voice"], cfg) if vkey in p else vkey
            said = [t for t in texts if t not in words]
            print(f"== {name}（{len(said)} 句" + (f"，外加 {len(texts) - len(said)} 个数字词，用来念金额" if len(said) < len(texts) else "") + "）")
            for t in said:
                print("  · " + t)
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
    if system.WINDOWS and not system.ffmpeg() and not system.fetch_ffmpeg():   # before paying, not halfway
        sys.exit("ffmpeg 下载不下来。手动装一个（winget install Gyan.FFmpeg），或把已有的 ffmpeg.exe 放到 "
                 + system.FFMPEG_HOME + "，再重跑同一条命令")
    done, failed = rooyun.record(client, jobs)
    print(f"录好 {done} 句" + (f"，{failed} 句没录成（重跑同一条命令补录）" if failed else ""))
    if pending and not failed:
        switch_voice(*pending)


def cmd_agent(a):
    from . import agents
    if a.action == "install":
        if a.which not in ("claude", "codex"):
            print(agents.setup_text(a.name or ""))   # any other agent wires its own hook to `bobao agent done`
            return
        print(agents.install(a.which))
        print("试一下：bobao agent done --name " + ("Claude Code" if a.which == "claude" else "Codex"))
        return
    if a.action == "setup":
        print(agents.setup_text(a.name or ""))
        return
    if a.action == "watch":
        if not a.name or not (a.dir or a.off):
            raise SystemExit("用法：bobao agent watch --name 你的名字 --dir 会话记录所在的文件夹 [--idle 秒] [--done 结尾的正则]；停止：--off")
        print(agents.watch(a.name, a.dir, a.idle, a.done, a.off))
        return
    agents.hook([a.action, a.which or ""] + list(a.rest), a.name or "")   # run by the hooks themselves


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
    print("后台要在运行（bobao install）；第一次有人打开时，" + ("Windows 防火墙可能弹窗，勾选「专用网络」并点允许"
          if system.WINDOWS else "macOS 可能问是否允许 python3 接受连接，点允许"))
    if not a.no_open:
        system.open_url(shout.qr_page(urls))


PAGE = "https://funengzhe.github.io/bobao/"


def recommend_text(cfg, user):
    """What to suggest once Bobao is set up: real voices (the computer's own sounds flat),
    scenes not picked yet, and the fun extras."""
    import urllib.parse
    rec, by_name = recommendations(), {v["name"]: v for v in catalog()}
    scenes = config.scene_names(user) or ["blank"]
    packs = config.list_packs("scenes")
    out = []
    if cfg["engine"] != "rooyun":
        out += ["现在用的是电脑自带的声音，听起来比较生硬。强烈建议换成真人一样的声音：用 RooYun（如云）把你的说法生成一次，",
                "一般一两个积分，生成前先报价；之后一直免费播，断网也能念。", ""]
        for name, p in rec.get("presets", {}).items():
            out.append(f"  ★ {name}：{p['desc']}")
            out.append(f"      bobao voice use {name}")
        for sc in scenes:
            picks = [n for n in rec.get("scenes", {}).get(sc, []) if n in by_name]
            if picks:
                title = packs.get(sc, {}).get("name", sc)
                out.append(f"  适合「{title}」：" + "、".join(f"{n}（{'、'.join(by_name[n]['tags'])}）" for n in picks))
                out += [f"      先听：bobao voice listen {n}    网页：{PAGE}#voice-{urllib.parse.quote(n)}"
                        for n in picks[:1]]
        out += [f"  全部 22 个声音：{PAGE}#voices   也可以用你自己或家人的声音（RooYun 克隆）", ""]
    rest = [p["name"] for k, p in packs.items() if k not in scenes and k != "blank"]
    if rest:
        out += ["还能加的场景：" + "、".join(rest) + "（跟智能体说「再加上直播的提醒」）", ""]
    out.append("还能这样玩：")
    out += [f"  · {t}：{d}。{how}" for t, d, how in rec.get("fun", [])]
    return "\n".join(out)


def cmd_recommend(a):
    print(recommend_text(config.load(), config.read_json(paths.CONFIG, {}) or {}))


def cmd_sounds(a):
    print("已生成音效：" + "、".join(sounds.make_all()) + f"（在 {paths.SOUNDS}）")


def running():
    if system.WINDOWS:
        return bool(system.running_pid())
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{AGENT}"], capture_output=True, text=True)
    return "state = running" in r.stdout


def cmd_status(a):
    print("后台：" + ("运行中" if running() else "没有运行（bobao install 安装）"))
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


def windows_sources(picked):
    """Windows reads no popups yet: Feishu is read through its API instead."""
    if not system.WINDOWS or "notifications" not in picked:
        return list(picked)
    return list(dict.fromkeys(["feishu" if s == "notifications" else s for s in picked]))


def apply_sources(user, picked, apps=None, chats=None, before=()):
    if system.WINDOWS and "notifications" in picked:
        print("Windows 上还读不了 App 的弹窗，改成读飞书（用你自己的身份：bobao feishu me）。微信暂时不支持")
        picked = windows_sources(picked)
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


def enabled_sources(user):
    """What a saved setup uses now, in init's terms (empty for a new one)."""
    if "sources" not in user:
        return []
    on = [n for n in ("notifications", "feishu", "webhook") if user["sources"].get(n, {}).get("enabled")]
    return on + (["remind"] if user.get("reminders") else [])


def summary(user, picked):
    cfg = config.load()
    names = [config.list_packs("scenes").get(n, {}).get("name", n) for n in config.scene_names(user)]
    voice = "RooYun · " + config.voice_for(cfg, "提醒")["voice"] if cfg["engine"] == "rooyun" else "电脑自带"
    print(f"已保存 {paths.CONFIG}：场景 {'、'.join(names) or '无'}，风格 {cfg['styleName']}，称呼 {cfg['称呼']}，"
          f"声音 {voice}，来源 {'、'.join(picked)}" + (f"，定时提醒 {len(cfg['reminders'])} 条" if cfg["reminders"] else ""))
    offer = [r for r in cfg["suggestedReminders"] if r not in cfg["reminders"]]
    if offer:
        print("场景里有这些定时提醒，没有打开，他想要再加（bobao remind add 时间 \"说法\" --days ...）：")
        for r in offer:
            print(f"  {when_text(r)} {r['at']}  {r['say']}")
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
    summary(user, windows_sources(picked))


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
    popups = ("（Windows 上还读不了，选了也不会念）" if system.WINDOWS else "")
    picked = choose("选择", [("电脑上的弹窗：飞书、企业微信、钉钉、微信、日历、邮件…" + popups, "notifications"),
                             ("飞书群（用你自己的身份读，或建一个「飞书播报」机器人，见 AGENTS.md）", "feishu"),
                             ("你自己的系统推过来（Webhook）", "webhook"),
                             ("定时提醒（例如工作日六点提醒下班）", "remind")],
                    ",".join(str(i) for i, s in enumerate(("notifications", "feishu", "webhook", "remind"), 1)
                             if s in windows_sources(first.get("suggestSources", ["notifications"]))))
    apps = None
    if "notifications" in picked:
        default = [x for sc in user["scenes"] for x in SCENE_APPS.get(sc, [])]
        apps = choose("  读哪些 App 的弹窗", APPS, ",".join(str(i) for i, (_, k) in enumerate(APPS, 1) if k in default) or "1")
    if not user.get("称呼"):   # each scene has its own form of address; change it later if you like
        user.pop("称呼", None)
    apply_sources(user, picked, apps)
    config.save_user(user)
    sounds.make_all()
    summary(user, windows_sources(picked))
    print("\n下一步：bobao install 装好（会播一句安装提示）。想换好听的声音：打开 https://funengzhe.github.io/bobao/ 挑一个，"
          "再 bobao voice use 名字。")


DAYS = {"每天": None, "工作日": [1, 2, 3, 4, 5], "周末": [6, 7]}


def when_text(r):
    days = r.get("days")
    if not days or sorted(days) == list(range(1, 8)):
        return "每天"
    return next((k for k, d in DAYS.items() if d == days), "周" + "、".join(map(str, days)))


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
    loaded = config.load()
    current = loaded["reminders"]
    if a.action == "list":
        if not current:
            print("还没有定时提醒。添加：bobao remind add 18:00 \"下班啦\" --days 工作日")
        for i, r in enumerate(current, 1):
            print(f"  {i}. {when_text(r)} {r['at']}  {r['say']}")
        offer = [r for r in loaded["suggestedReminders"] if r not in current]
        if offer:
            print("场景建议的（没打开）：")
            for r in offer:
                print(f"     {when_text(r)} {r['at']}  {r['say']}")
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
    if a.action in ("connect", "me"):   # read as yourself: lark-cli logged in as you, no bot
        cli = feishu.lark_cli(src)
        if not feishu.found(cli):
            raise SystemExit("没有找到 lark-cli。先安装（国内用镜像快）：npm install -g @larksuite/cli "
                             "--registry=https://registry.npmmirror.com ，没有 npm 就先装 Node。装好再运行 bobao feishu connect")
        src["larkCli"] = os.path.abspath(shutil.which(cli) or cli)   # the background may start with an older PATH
        if a.action == "connect":
            feishu.connect(src, say=lambda t: print(t, flush=True))
        if src.get("profile"):
            src["botProfile"] = src.pop("profile")   # kept, to switch back
        src["enabled"] = True
        if a.chats:
            src["chats"] = split(a.chats)
        if a.people:
            src["botsOnly"] = False
        user.setdefault("sources", {})["feishu"] = src
        config.save_user(user)
        print("改成以你自己的身份读飞书" + ("（人发的消息也算）" if src.get("botsOnly") is False else "（只看机器人发的通知；人发的也要念就加 --people）"))
    me = not src.get("profile")
    if me and src.get("enabled") is not True:
        raise SystemExit("还没有连接飞书：用机器人 bobao feishu login --app cli_xxx，或用你自己 bobao feishu me")
    try:
        chats = feishu.lark(src, "im", "+chat-list", "--page-all").get("chats") or []
    except Exception as e:
        raise SystemExit(f"读不到群：{e}\n" + ("确认已运行 lark-cli auth login 并登录了你的飞书" if me else
                                           "检查开放平台里是否开通了「查看群信息」等权限，并已发布版本。"))
    if me:
        listed = src.get("chats") or []
        print("你所在的群（只播 --chats 列出的" + ("：" + "、".join(listed) if listed else "，现在一个都没列，加上：bobao feishu me --chats 群名") + "）：")
        for c in chats[:80]:
            print(f"  {c['name']}{'  ✓' if c['name'] in listed else ''}")
        return
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
    if any(not os.path.exists(os.path.join(paths.SOUNDS, slug + ".wav")) for slug, *_ in sounds.SOUNDS.values()):
        sounds.make_all()   # first install, or a version that added sounds
    if system.WINDOWS:
        return install_windows(a, here)
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
    if not a.quiet:   # the install greeting: a soft chime, then 小柚
        play_files(os.path.join(paths.SOUNDS, "chime.wav"), os.path.join(here, "assets", "welcome.mp3"))
    print("\n" + recommend_text(cfg, config.read_json(paths.CONFIG, {}) or {}))


# Windows: the background runs from a copy too, started by a shortcut in the Startup folder.
RUN_PYW = """import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
os.environ.setdefault("BOBAO_HOME", {home!r})
sys.stdout = sys.stderr = open(os.path.join(os.environ["BOBAO_HOME"], "bobao.log"), "a", encoding="utf-8", buffering=1)
from bobao import daemon
daemon.run()
"""
CLI_PY = """import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOBAO_HOME", {home!r})
from bobao.__main__ import main
main()
"""


def install_windows(a, here):
    run = os.path.join(paths.APP, "bobao_run.pyw")
    for path, text in ((run, RUN_PYW), (os.path.join(paths.APP, "bobao_cli.py"), CLI_PY)):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.format(home=paths.HOME))
    where = system.install_startup(run, paths.APP)
    print(f"后台已启动，登录 Windows 时自动运行（{where}）。日志：{paths.LOG}")
    if config.load()["sources"]["notifications"].get("enabled"):
        print("提示：Windows 上暂时还读不了其他 App 的弹窗，请用飞书机器人、Webhook 或定时提醒")
    if not any(lang.lower().startswith("zh") for _, lang in system.voices()):
        print("这台电脑自带的声音里没有中文，念出来会不对。请打开 设置 → 时间和语言 → 语音 → 添加语音，"
              "选「中文（简体，中国）」，装好后不用重装 Bobao")
    if not a.quiet:
        play_files(os.path.join(paths.SOUNDS, "chime.wav"), os.path.join(here, "assets", "welcome.mp3"))
    print("\n" + recommend_text(config.load(), config.read_json(paths.CONFIG, {}) or {}))


def cmd_uninstall(a):
    if system.WINDOWS:
        system.remove_startup()
        print(f"已停止并移除开机启动。设置和录音还在 {paths.HOME}，不要了可以整个删掉。")
        return
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
    for name in ("run", "uninstall", "status", "packs", "sounds", "recommend"):
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
    fe.add_argument("action", choices=["connect", "login", "groups", "me"])
    fe.add_argument("--chats", help="me：只播这些群（逗号隔开）")
    fe.add_argument("--people", action="store_true", help="me：人发的消息也念（默认只念机器人的通知）")
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
    ag.add_argument("action", help="done / waiting（任何智能体的钩子用）、install claude|codex、setup、watch")
    ag.add_argument("which", nargs="?")
    ag.add_argument("rest", nargs="*")
    ag.add_argument("--name", help="是哪个智能体（你自己的名字）")
    ag.add_argument("--dir", help="watch：会话记录所在的文件夹")
    ag.add_argument("--idle", type=int, help="watch：文件停止增长多少秒算做完（默认 15）")
    ag.add_argument("--done", help="watch：这一轮结束时文件末尾会出现的内容（正则），有它更准")
    ag.add_argument("--off", action="store_true", help="watch：不再看")
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
    v.add_argument("action", choices=["plan", "quote", "record", "use", "listen"])
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
            system.open_url(f"http://127.0.0.1:{a.port}")
        return server.serve_forever()
    if a.cmd == "review":
        from . import review
        return review.serve(a.port, not a.no_open)
    {"init": cmd_init, "install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status, "packs": cmd_packs,
     "voices": cmd_voices, "sounds": cmd_sounds, "test": cmd_test, "replay": cmd_replay, "send": cmd_send,
     "rooyun": cmd_rooyun, "voice": cmd_voice, "feishu": cmd_feishu, "export": cmd_export,
     "import": cmd_import, "remind": cmd_remind, "notifications": cmd_notifications, "agent": cmd_agent,
     "github": cmd_github, "clip": cmd_clip, "shout": cmd_shout, "recommend": cmd_recommend}[a.cmd](a)


if __name__ == "__main__":
    main()
