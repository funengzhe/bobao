"""Bobao 定制播报 — your notifications, read aloud the way you want.

  bobao init                      set up: form of address, style, voice, sources
  bobao init --scene saas --style formal --name 老板 --engine mac --sources feishu,webhook
                                  the same without questions (for scripts and agents)
  bobao feishu login --app cli_xxx
                                  connect your 飞书播报 bot; the App Secret is read from
                                  stdin (pbpaste | bobao feishu login ...) or asked hidden
  bobao feishu groups             the groups the bot was added to
  bobao run                       run in the foreground (the agent runs this)
  bobao install | uninstall       start at login / stop for good
  bobao status                    is it running, what was said lately

  bobao test "<title>" [-f 金额=$19.9 ...] [--channel 群名] [--play]
                                  what a notification would be classified and said as
  bobao replay [--chat 群名] [--limit 30]
                                  run a Feishu group's recent messages through the rules
  bobao send "<title>" [-f k=v ...] [--type 收款 --platform X]
                                  post a test notification to the local webhook

  bobao packs                     list style and rule packs
  bobao voices                    list RooYun voices (system and your own)
  bobao rooyun login              connect your RooYun account
  bobao voice plan                every sentence your setup can say, and what is unrecorded
  bobao voice quote               price of recording what is missing
  bobao voice record [--yes]      record it (asks first, shows the price)
  bobao gallery                   listen to every scene, style, voice and emotion before choosing
  bobao review                    listen to everything, mark pieces to re-record
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
        print(f"播报（{config.voice_key(v)}）：{t}")
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


def cmd_voices(a):
    from .rooyun import Client
    cfg = config.load()
    for v in Client(cfg["rooyun"]["base"]).voices():
        print(f"{v['voiceId']:32} {v['name']}  {'（你的音色）' if v.get('kind') == 'user' else ''}")


def cmd_rooyun(a):
    from . import rooyun
    cfg = config.load()
    if a.action == "login":
        rooyun.login(cfg["rooyun"]["base"])
    else:
        me = rooyun.Client(cfg["rooyun"]["base"]).me()
        print(json.dumps({k: me.get(k) for k in ("userId", "scopes", "expiresAt")}, ensure_ascii=False))


def cmd_voice(a):
    cfg = config.load()
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
        return
    from . import rooyun
    client = rooyun.Client(cfg["rooyun"]["base"])
    meta = {v["voiceId"]: v for v in client.voices()}
    jobs = rooyun.jobs_for(todo, client, cfg, meta)
    price, available = rooyun.quote(client, jobs)
    minutes = round(len(jobs) * rooyun.SUBMIT_GAP / 60)
    print(f"要录 {len(jobs)} 句，约 {price} 积分，你的可用积分 {round(available, 2)}（如云每分钟最多提交 10 句，约 {minutes} 分钟）")
    if a.action == "quote":
        return
    if price > available:
        sys.exit("积分不够，请先到如云充值")
    if not a.yes and input("开始录吗？[y/N] ").strip().lower() not in ("y", "yes", "是"):
        print("没有录")
        return
    done, failed = rooyun.record(client, jobs)
    print(f"录好 {done} 句" + (f"，{failed} 句没录成（重跑同一条命令补录）" if failed else ""))


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
APPS = [("微信", "com.tencent.xinWeChat"), ("企业微信", "com.tencent.WeWorkMac"), ("钉钉", "com.alibaba.DingTalkMac"),
        ("邮件", "com.apple.mail"), ("Slack", "com.tinyspeck.slackmacgap")]


def ask(q, default=""):
    v = input(f"{q}" + (f" [{default}]" if default else "") + "：").strip()
    return v or default


def choose(q, options, default=1):
    for i, (label, _) in enumerate(options, 1):
        print(f"  {i}. {label}")
    v = ask(q, str(default))
    picks = [int(x) for x in v.replace("，", ",").replace(" ", ",").split(",") if x.strip().isdigit()]
    return [options[i - 1][1] for i in picks if 0 < i <= len(options)]


def init_quiet(a):
    """bobao init with flags: no questions, unset flags keep the current value or the scene's."""
    user = config.read_json(paths.CONFIG, {}) or {}
    scenes, styles, packs = config.list_packs("scenes"), config.list_packs("styles"), config.list_packs("rules")
    for value, known, what in ((a.scene, scenes, "场景"), (a.style, styles, "风格")):
        if value and value not in known:
            raise SystemExit(f"没有这个{what}：{value}（可选：{'、'.join(known)}）")
    if a.scene is not None:
        user["scene"] = a.scene
    scene = scenes.get(user.get("scene"), {})
    user["style"] = a.style or user.get("style") or scene.get("style") or "formal"
    if a.name:
        user["称呼"] = a.name
    user["engine"] = a.engine or user.get("engine") or "mac"
    if a.rule_packs:
        user["rulePacks"] = [x for x in a.rule_packs.split(",") if x]
        for x in user["rulePacks"]:
            if x not in packs:
                raise SystemExit(f"没有这个规则包：{x}（可选：{'、'.join(packs)}）")
    picked = a.sources.split(",") if a.sources else scene.get("suggestSources", ["webhook"])
    src = user.setdefault("sources", {})
    for name in ("feishu", "webhook", "notifications"):
        src[name] = dict(src.get(name, {}), enabled=name in picked)
    if a.chats:
        src["feishu"]["chats"] = [x for x in a.chats.split(",") if x]
    config.save_user(user)
    sounds.make_all()
    cfg = config.load()
    print(f"已保存 {paths.CONFIG}：场景 {user.get('scene') or '无'}，风格 {cfg['styleName']}，称呼 {cfg['称呼']}，"
          f"声音 {'如云' if cfg['engine'] == 'rooyun' else 'Mac 自带'}，来源 {'、'.join(n for n in picked)}")


def cmd_init(a):
    if any(v is not None for v in (a.scene, a.style, a.name, a.engine, a.sources, a.rule_packs, a.chats)) or a.yes:
        return init_quiet(a)
    user = config.read_json(paths.CONFIG, {}) or {}
    print("Bobao 定制播报 · 设置（直接回车用括号里的默认值）\n")
    scenes = config.list_packs("scenes")
    print("0) 你是哪类用户？选一个场景，播哪些类型、什么时段播、默认风格和音色都会配好")
    picked_scene = choose("选一个", [(f"{p['name']}（{p['who']}）：{p['description']}", k) for k, p in scenes.items()]
                          + [("自己从头配", "")], "1")
    scene = scenes.get(picked_scene[0], {}) if picked_scene else {}
    user["scene"] = picked_scene[0] if picked_scene else ""
    styles = config.list_packs("styles")
    names = list(styles)
    print("1) 播报风格（试听：bobao gallery）")
    default = names.index(scene["style"]) + 1 if scene.get("style") in names else names.index("formal") + 1
    style = choose("选一个", [(f"{p.get('name')}：{p.get('description')}", k) for k, p in styles.items()], default)
    user["style"] = (style or ["formal"])[0]
    user["称呼"] = ask("2) 怎么称呼你（老板、哥哥、名字…）", user.get("称呼") or scene.get("称呼") or styles[user["style"]].get("称呼", "老板"))
    print("3) 声音")
    user["engine"] = (choose("选一个", [("Mac 自带声音（免费，马上能用）", "mac"),
                                        ("如云配音（好听、可选音色或用你自己的声音，一整套只要几个积分，录一次永久免费播放）", "rooyun")]) or ["mac"])[0]
    src = user.setdefault("sources", {})
    print("4) 从哪里收通知（可多选，用逗号隔开）")
    picked = choose("选择", [("飞书群（需要 lark-cli）", "feishu"), ("Webhook：你的系统直接推过来", "webhook"),
                             ("系统通知：微信、钉钉、邮件等的弹窗", "notifications")],
                    ",".join(str(i) for i, s in enumerate(("feishu", "webhook", "notifications"), 1)
                             if s in scene.get("suggestSources", ["webhook"])))
    src["webhook"] = dict(src.get("webhook", {}), enabled="webhook" in picked)
    if "feishu" in picked:
        from .sources.feishu import lark
        app = ask("  飞书播报机器人的 App ID（推荐，见 README「接飞书」；留空则用你自己的 lark-cli 登录）", "")
        if app:
            src["feishu"] = dict(src.get("feishu", {}), enabled=True, app=app)
            print(f"  设置完后运行：pbpaste | bobao feishu login --app {app}（先复制 App Secret）")
    if "feishu" in picked and not src.get("feishu", {}).get("app"):
        try:
            chats = [c["name"] for c in (lark({}, "im", "+chat-list", "--page-all").get("chats") or [])]
        except Exception as e:
            chats = []
            print(f"  读不到飞书群（{e}）。先安装并登录 lark-cli，再重新运行 bobao init")
        if chats:
            names = choose("  要播哪几个群（逗号隔开）", [(c, c) for c in chats[:40]], "")
            src["feishu"] = dict(src.get("feishu", {}), enabled=bool(names), chats=names)
    if "notifications" in picked:
        apps = choose("  哪些 App 的通知（逗号隔开）", APPS, "1")
        src["notifications"] = dict(src.get("notifications", {}), enabled=True, apps=apps)
    packs = config.list_packs("rules")
    print("5) 通知规则包（可多选，按顺序生效）")
    user["rulePacks"] = choose("选择", [(f"{p.get('name')}：{p.get('description')}", k) for k, p in packs.items()],
                               ",".join(str(i) for i, k in enumerate(packs, 1) if k == "generic") or "1")
    config.save_user(user)
    sounds.make_all()
    print(f"\n已保存到 {paths.CONFIG}，可以直接改这个文件来定制每一类的说法、音色、音效和夜间时段。")
    if user["engine"] == "rooyun":
        print("下一步：bobao rooyun login → bobao voice record → bobao review → bobao install")
    else:
        print("下一步：bobao test \"充值到账\" -f 金额=\\$19.9 --play  试听，满意后 bobao install")


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
    print("里面没有飞书 App Secret 和如云登录；对方导入后要自己运行一次 bobao feishu login。"
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
    for name in ("run", "install", "uninstall", "status", "packs", "voices", "sounds"):
        sub.add_parser(name)
    i = sub.add_parser("init")
    i.add_argument("--scene")
    i.add_argument("--style")
    i.add_argument("--name", help="怎么称呼你")
    i.add_argument("--engine", choices=["mac", "rooyun"])
    i.add_argument("--sources", help="feishu,webhook,notifications")
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
    ry = sub.add_parser("rooyun")
    ry.add_argument("action", choices=["login", "me"])
    v = sub.add_parser("voice")
    v.add_argument("action", choices=["plan", "quote", "record"])
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
        print("正在用这台 Mac 的声音生成试听…")
        subprocess.run(["/usr/bin/python3", os.path.join(root, "tools", "make_gallery.py"), "--mac"], capture_output=True)
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
     "import": cmd_import}[a.cmd](a)


if __name__ == "__main__":
    main()
