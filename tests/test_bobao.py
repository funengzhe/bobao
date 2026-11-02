"""python3 -m unittest discover tests"""

import os
import random
import tempfile
import time
import unittest

os.environ["BOBAO_HOME"] = tempfile.mkdtemp(prefix="bobao-test-")

from bobao import clips, compose, config, daemon  # noqa: E402
from bobao.events import Event, classify  # noqa: E402
from bobao.numbers import cn_number, money, vocabulary  # noqa: E402
from bobao.sources import feishu  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
USER = {"rulePacks": [os.path.join(FIXTURES, "alpha.json"), os.path.join(FIXTURES, "beta.json"), "generic"],
        "platforms": {"Alpha": {"say": "Alpha", "channels": ["a"]}, "Beta": {"say": "贝塔", "channels": ["b"]}},
        "bigOrder": {"Alpha": 100, "Beta": 500}}


def cfg_for(style, **extra):
    return config.load(dict(USER, style=style, **extra))


def ev(title, channel="a", **fields):
    return Event("feishu", channel, title, fields=fields, bot=True)


class Numbers(unittest.TestCase):
    def test_spoken(self):
        cases = {"2": "两", "12": "十二", "200": "两百", "2000": "两千", "20000": "两万", "105": "一百零五",
                 "5.35": "五点三五", "2.5": "二点五", "1010": "一千零一十", "39": "三十九"}
        for n, s in cases.items():
            self.assertEqual(cn_number(n), s, n)

    def test_money(self):
        self.assertEqual(money("$19.90"), "19.9 美元")
        self.assertEqual(money("¥99.00"), "99 元")
        self.assertEqual(money("9.9 USD"), "9.9 美元")


class Rules(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg_for("playful")

    def kind(self, e):
        m, _ = classify(e, self.cfg)
        return m and (m.type, m.platform)

    def test_platform_cards(self):
        self.assertEqual(self.kind(ev("[Alpha] 充值到账")), ("收款", "Alpha"))
        self.assertEqual(self.kind(ev("[Beta] 套餐购买到账", "b")), ("套餐", "Beta"))
        self.assertEqual(self.kind(ev("[Beta] 已恢复：接口", "b")), ("恢复", "Beta"))

    def test_rules_stay_in_their_group(self):
        # 通道熔断 is a Beta alert; in the Alpha group only the generic net may catch it
        self.assertEqual(self.kind(ev("【警告】通道熔断", "b")), ("告警", "Beta"))
        m, _ = classify(ev("【警告】通道熔断", "a"), self.cfg)
        self.assertNotEqual(m.platform, "Beta")

    def test_skips(self):
        self.assertIsNone(self.kind(ev("【模拟】Alpha 充值到账 9.9 USD")))
        self.assertIsNone(self.kind(ev("[Beta] 本周注册全部来自测试账号", "b")))
        self.assertIsNone(self.kind(ev("今天天气不错")))

    def test_people_are_not_read(self):
        m = {"content": "测试到账1元", "sender": {"sender_type": "user"}, "create_time": "2026-11-02 10:00"}
        self.assertIs(feishu.to_event("a", m).bot, False)

    def test_amountless_payment_is_not_misread(self):
        utt, _ = daemon.decide(ev("[Beta] 充值到账", "b"), self.cfg, dry=True)
        self.assertNotIn("到账", utt["text"])   # says only that a notification came in

    def test_catch_all(self):
        utt, _ = daemon.decide(ev("某某服务宕机"), self.cfg, dry=True)
        self.assertEqual(utt["type"], "告警")
        utt, _ = daemon.decide(ev("提现失败了"), self.cfg, dry=True)
        self.assertEqual(utt["type"], "通知")


class Gates(unittest.TestCase):
    def test_quiet_cooldown_stale(self):
        cfg = cfg_for("formal", types={"注册": {"quietHours": "00:00-23:59"}})
        daemon.last_spoken.clear()
        self.assertIn("夜间", daemon.decide(ev("[Alpha] 新用户注册"), cfg)[1])
        a = ev("支付通道熔断")
        self.assertIsNotNone(daemon.decide(a, cfg)[0])
        self.assertIn("冷却", daemon.decide(a, cfg)[1])
        old = ev("[Beta] 经营日报", "b")
        old.time = time.time() - 3600
        self.assertIn("过期", daemon.decide(old, cfg)[1])
        self.assertNotIn((-1, ""), daemon.last_spoken)


class Coverage(unittest.TestCase):
    """Whatever render() can say, plan() has asked to record: with a library holding exactly
    the planned phrases, every rendering of every card must stitch completely."""

    def test_every_style(self):
        for style in config.list_packs("styles"):
            cfg = cfg_for(style, engine="rooyun")
            plan = compose.plan(cfg)
            lib = {vk: {clips.key(t): "x.wav" for t in e["phrases"] + (vocabulary() if e["numbers"] else [])}
                   for vk, e in plan.items()}
            cards = [ev("[Alpha] 充值到账", 支付金额=f"${a}", 支付方式=m, 备注=n)
                     for a in ("0.5", "2", "19.90", "120", "1234.56", "20000") for m in ("微信支付", "Stripe 银行卡", "USDT · TRC20", "") for n in ("首次充值", "")]
            cards += [ev("[Beta] 套餐购买到账", "b", 金额=f"¥{a}", 套餐=p) for a in ("39", "999") for p in ("会员·基础", "会员·创作者")]
            cards += [ev(t) for t in ("[Alpha] 新用户注册", "[Alpha] 经营日报", "支付通道熔断", "商品没有定价", "订单已取消", "[Alpha] 已恢复")]
            cards += [ev(t, "b") for t in ("[Beta] 新用户注册", "通道熔断", "待审批：退款", "[Beta] 充值到账", "任务进程掉线")]
            cards += [ev("莫名其妙的故障")]
            for card in cards:
                for seed in range(25):
                    utt, why = daemon.decide(card, cfg, dry=True, rnd=random.Random(seed))
                    self.assertIsNotNone(utt, (style, card.title, why))
                    found = clips.for_segments(utt["segments"], lib)
                    self.assertIsNotNone(found, (style, utt["text"]))


def library(cfg):
    """Exactly what plan() asks to record."""
    return {vk: {clips.key(t): "x" for t in e["phrases"] + (vocabulary() if e["numbers"] else [])}
            for vk, e in compose.plan(cfg).items()}


def matching_event(rule):
    """An event that the rule's `when` matches."""
    w = rule["when"]
    first = lambda k: (w[k] if isinstance(w[k], str) else w[k][0]) if k in w else ""
    source = first("source") or "webhook"
    return Event(source, first("app") or first("channel"), first("title") or "通知", text=first("text"), bot=True)


class Scenes(unittest.TestCase):
    def test_every_scene_loads_and_speaks(self):
        for name in config.list_packs("scenes"):
            cfg = config.load({"scenes": [name], "engine": "rooyun"})
            self.assertTrue(cfg["types"], name)
            lib = library(cfg)
            for title, f in (("充值到账", {"金额": "$19.9", "方式": "支付宝"}), ("新用户注册", {}), ("服务器宕机", {}), ("已恢复", {})):
                utt, why = daemon.decide(Event("webhook", "", title, fields=f), cfg, dry=True, rnd=random.Random(1))
                if utt:
                    self.assertIsNotNone(clips.for_segments(utt["segments"], lib), (name, utt["text"]))

    def test_scene_rules_and_reminders_are_recorded(self):
        """Every scene rule fires on its own example and says something already planned."""
        for name in config.list_packs("scenes"):
            cfg = config.load({"scenes": [name], "engine": "rooyun", "schedule": {},   # Bobao's own rules too
                               "agents": {"enabled": True}, "sources": {"github": {"enabled": True}}})
            lib = library(cfg)
            spoken = [r for r in cfg["rules"] if not r.get("skip") and cfg["types"].get(r["type"], {}).get("enabled") is not False]
            for i, rule in enumerate(spoken):
                daemon.last_spoken.clear()
                utt, why = daemon.decide(matching_event(rule), cfg, dry=True, rnd=random.Random(i))
                self.assertIsNotNone(utt, (name, rule["when"], why))
                self.assertIsNotNone(clips.for_segments(utt["segments"], lib), (name, utt["text"]))
            for r in cfg["reminders"]:
                utt = daemon.reminder_utterance(cfg, r)
                self.assertIsNotNone(clips.for_segments(utt["segments"], lib), (name, utt["text"]))

    def test_user_overrides_scene(self):
        cfg = config.load({"scenes": ["dev"], "types": {"收款": {"enabled": True}}, "称呼": "小王"})
        self.assertIsNot(cfg["types"]["收款"].get("enabled"), False)
        self.assertEqual(cfg["称呼"], "小王")
        self.assertEqual(cfg["style"], "formal")
        self.assertEqual(config.load({"scene": "dev"})["style"], "formal")   # the old single key still works

    def test_several_scenes_add_up(self):
        work, life = (config.load({"scenes": [n]}) for n in ("work", "life"))
        mine = {"when": {"title": ["周报"]}, "type": "通知", "skip": True}
        both = config.load({"scenes": ["上班", "life"], "rules": [mine]})
        self.assertEqual(both["style"], work["style"])           # the first scene sets the tone
        self.assertEqual(both["rules"][0], mine)                  # the user's rules come first
        for r in work["rules"] + life["rules"]:
            self.assertIn(r, both["rules"])
        self.assertEqual(len(both["reminders"]), len(work["reminders"]) + len(life["reminders"]))
        own = [{"at": "09:00", "say": "早"}]
        self.assertEqual(config.load({"scenes": ["work", "life"], "reminders": own})["reminders"], own)
        self.assertEqual(config.load({"scenes": ["work"], "reminders": []})["reminders"], [])


class Popups(unittest.TestCase):
    def test_app_condition(self):
        cfg = config.load({"scenes": ["work"]})
        at = lambda app: classify(Event("notifications", app, "张三", text="张三在群里@你"), cfg)[0]
        self.assertIsNotNone(at("com.electron.lark"))
        self.assertIsNotNone(at("com.tencent.WeWorkMac"))
        self.assertIsNone(at("com.tencent.xinWeChat"))

    def test_name_in_words(self):
        cfg = config.load({"scenes": ["work"], "称呼": "小王"})
        popup = Event("notifications", "com.tencent.WeWorkMac", "群聊", text="李四: @小王 看下这个")
        self.assertIsNotNone(classify(popup, cfg)[0])
        self.assertIsNone(classify(popup, config.load({"scenes": ["work"], "称呼": "老李"}))[0])


class Reminders(unittest.TestCase):
    def test_due_once_on_its_days(self):
        cfg = {"reminders": [{"at": "18:00", "days": [1, 2, 3, 4, 5], "say": "下班"}, {"at": "18:00", "say": "每天"}]}
        monday = time.strptime("2026-11-02 18:00", "%Y-%m-%d %H:%M")
        sunday = time.strptime("2026-11-08 18:00", "%Y-%m-%d %H:%M")
        fired = set()
        self.assertEqual([r["say"] for r in daemon.due_reminders(cfg, monday, fired)], ["下班", "每天"])
        self.assertEqual(daemon.due_reminders(cfg, monday, fired), [])
        self.assertEqual([r["say"] for r in daemon.due_reminders(cfg, sunday, fired)], ["每天"])
        self.assertEqual(daemon.due_reminders(cfg, time.strptime("2026-11-02 18:01", "%Y-%m-%d %H:%M"), set()), [])

    def test_names_are_filled(self):
        cfg = config.load({"scenes": ["work"], "称呼": "小王"})
        utt = daemon.reminder_utterance(cfg, {"at": "09:00", "say": "{称呼}，早上好"})
        self.assertEqual(utt["text"], "小王，早上好")


class Schedule(unittest.TestCase):
    def test_days_hours_always(self):
        now = time.strftime("%H:%M")
        today = time.localtime().tm_wday + 1
        other = [d for d in range(1, 8) if d != today]
        cfg = cfg_for("formal", schedule={"days": other})
        self.assertIn("播报日", daemon.decide(ev("[Alpha] 新用户注册"), cfg)[1])
        cfg = cfg_for("formal", schedule={"days": other}, types={"注册": {"always": True}})
        daemon.last_spoken.clear()
        self.assertIsNotNone(daemon.decide(ev("[Alpha] 新用户注册"), cfg)[0])
        cfg = cfg_for("formal", types={"注册": {"hours": "00:00-00:00" if now != "00:00" else "01:00-01:01"}})
        self.assertIn("时段", daemon.decide(ev("[Alpha] 新用户注册"), cfg)[1])


class FeishuBot(unittest.TestCase):
    def setUp(self):
        self.f = feishu.Feishu()
        self.f.push.profile = "bobao"   # as if its connection were already running
        self.f.ids = {"通知群": "oc_1", "外部群": "oc_2", "闲聊群": "oc_3"}
        self.f.ids_at = time.time()

    def cfg(self, chats=()):
        return {"sources": {"feishu": {"profile": "bobao", "chats": list(chats)}}}

    def test_identity_and_interval(self):
        self.assertEqual(feishu.identity({"profile": "bobao"}), (["--profile", "bobao"], "bot"))
        self.assertEqual(feishu.identity({}), ([], "user"))
        self.assertEqual(feishu.poll_seconds({"profile": "bobao"}), 300)
        self.assertEqual(feishu.poll_seconds({}), 20)

    def test_push_maps_to_groups(self):
        self.f.push.queue.put("oc_2")
        self.f.push.queue.put("oc_9")   # a chat the bot is not in
        self.assertEqual(self.f.pushed(self.cfg()), {"外部群"})
        self.assertEqual(self.f.pushed(self.cfg()), set())

    def test_reconnect_checks_every_listed_group(self):
        self.f.push.queue.put(feishu.EVERY)
        self.assertEqual(self.f.pushed(self.cfg(["通知群", "外部群"])), {"通知群", "外部群"})
        self.f.push.queue.put("oc_3")   # pushed, but not a group to announce
        self.assertEqual(self.f.pushed(self.cfg(["通知群"])), set())


if __name__ == "__main__":
    unittest.main()


class Agents(unittest.TestCase):
    def test_long_turn_speaks_short_one_does_not(self):
        from bobao import agents
        cfg = config.load({})
        agents.claude("prompt", {"session_id": "s1"}, cfg, now=1000)
        self.assertIsNone(agents.claude("stop", {"session_id": "s1", "cwd": "/x/shop"}, cfg, now=1010))
        agents.claude("prompt", {"session_id": "s1"}, cfg, now=2000)
        body = agents.claude("stop", {"session_id": "s1", "cwd": "/x/shop"}, cfg, now=2100)
        self.assertEqual(body["title"], "智能体完成")
        self.assertEqual(body["fields"]["项目"], "shop")

    def test_permission_speaks_idle_does_not(self):
        from bobao import agents
        cfg = config.load({})
        self.assertIsNone(agents.claude("notify", {"message": "Claude is waiting for your input"}, cfg))
        self.assertEqual(agents.claude("notify", {"message": "Claude needs your permission to use Bash"}, cfg)["title"],
                         "智能体等你确认")
        self.assertEqual(agents.codex({"type": "agent-turn-complete", "cwd": "/a/b"})["title"], "智能体完成")

    def test_claude_events_by_length_question_error_and_background(self):
        from bobao import agents
        cfg = config.load({})
        def stop(took, **data):
            agents.claude("prompt", {"session_id": "s2"}, cfg, now=10000)
            body = agents.claude("stop", dict(session_id="s2", **data), cfg, now=10000 + took)
            return body and body["title"]
        self.assertEqual(stop(120), "智能体完成")
        self.assertEqual(stop(15 * 60), "智能体完成·久")
        self.assertEqual(stop(45 * 60), "智能体完成·很久")
        self.assertEqual(stop(120, last_assistant_message="要我推送吗？"), "智能体提问")
        self.assertIsNone(stop(120, background_tasks=[{"id": "t1", "type": "subagent"}]))   # paused, not done
        failure = lambda err: agents.claude("failure", {"session_id": "s2", "error": err}, cfg)["title"]
        self.assertEqual(failure("rate_limit"), "智能体出错·额度")
        self.assertEqual(failure("authentication_failed"), "智能体出错·登录")
        self.assertEqual(failure("server_error"), "智能体出错")
        note = lambda t: (agents.claude("notify", {"notification_type": t}, cfg) or {}).get("title")
        self.assertEqual(note("permission_prompt"), "智能体等你确认")
        self.assertEqual(note("elicitation_dialog"), "智能体提问")
        self.assertEqual(note("quota_auto_resume_fired"), "智能体额度恢复")
        self.assertIsNone(note("idle_prompt"))
        on = config.load({"agents": {"enabled": True}})
        for title in ("智能体完成·很久", "智能体完成·久", "智能体提问", "智能体出错·额度", "智能体额度恢复"):
            utt, why = daemon.decide(Event("webhook", "Claude Code", title, bot=True), on, dry=True)
            self.assertTrue(utt and "Claude" in utt["text"] or "额度" in utt["text"], (title, why))

    def test_only_agents_in_use_are_recorded(self):
        said = lambda cfg: [t for e in compose.plan(cfg).values() for t in e["phrases"]]
        mine = said(config.load({"agents": {"enabled": True, "used": ["Claude Code"]}}))
        self.assertTrue(any("Claude" in t for t in mine))
        self.assertFalse(any("Codex" in t or "Cursor" in t or "智能体" in t for t in mine))

    def test_spoken_once_turned_on_recorded_only_then(self):
        on = config.load({"agents": {"enabled": True}})
        utt, why = daemon.decide(Event("webhook", "Claude Code", "智能体完成", bot=True), on, dry=True)
        self.assertTrue(utt and "Claude" in utt["text"] and "智能体" not in utt["text"], why)
        said = lambda cfg: [t for e in compose.plan(cfg).values() for t in e["phrases"]]
        self.assertTrue(any("智能体" in t for t in said(on)) and any("Claude" in t for t in said(on)))
        self.assertFalse(any("智能体" in t or "Claude" in t or "点星" in t for t in said(config.load({}))))

    def test_agent_named_as_said_unknown_ones_as_agent(self):
        rec = config.load({"agents": {"enabled": True, "names": {"WorkBuddy": "小助手"}}, "engine": "rooyun"})
        self.assertEqual(compose.spoken_agent(rec, "Claude Code"), "Claude")
        self.assertEqual(compose.spoken_agent(rec, "WorkBuddy"), "小助手")
        self.assertEqual(compose.spoken_agent(rec, "Trae"), "智能体")   # never recorded
        self.assertEqual(compose.spoken_agent(config.load({"agents": {"enabled": True}}), "Trae"), "Trae")


class GitHub(unittest.TestCase):
    def test_first_look_is_silent_then_increases_speak(self):
        from bobao.sources import github
        seen = {}
        self.assertEqual(github.changes("me/p", {"stargazers_count": 3, "forks_count": 1, "open_issues_count": 0}, seen), [])
        evs = github.changes("me/p", {"stargazers_count": 5, "forks_count": 1, "open_issues_count": 0}, seen)
        self.assertEqual([e.title for e in evs], ["新的 star"])
        cfg = config.load({"sources": {"github": {"enabled": True}}})
        utt, why = daemon.decide(evs[0], cfg, dry=True)
        self.assertTrue(utt and "星" in utt["text"], why)


class Shout(unittest.TestCase):
    def test_page_needs_token_and_speaks(self):
        import json as j
        import queue
        import socket
        import urllib.error
        import urllib.request
        from bobao import shout
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        cfg = config.load({"sources": {"shout": {"enabled": True, "token": "tok", "port": port}}})

        class FakeSpeaker:
            q = queue.Queue()

            def put(self, utt, c):
                self.q.put(utt)
        sp = FakeSpeaker()
        server = shout.serve(lambda: cfg, sp)
        try:
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/s/wrong")
            self.assertIn("喊一句", urllib.request.urlopen(f"http://127.0.0.1:{port}/s/tok").read().decode())
            req = urllib.request.Request(f"http://127.0.0.1:{port}/s/tok/say", j.dumps({"text": "开饭啦"}).encode(),
                                         {"content-type": "application/json"})
            self.assertTrue(j.load(urllib.request.urlopen(req))["ok"])
            self.assertEqual(sp.q.get_nowait()["text"], "开饭啦")
            with self.assertRaises(urllib.error.HTTPError) as e:   # one line per 3 seconds
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 429)
        finally:
            server.shutdown()


class WindowsFeishu(unittest.TestCase):
    def test_popup_line_nudges_and_feishu_rules_fire(self):
        from bobao.sources import winpopups
        self.assertEqual(winpopups.line_to_spool("POPUP\t产品群\r\n", now=1)["anyGroup"], True)
        self.assertIsNone(winpopups.line_to_spool("noise"))
        cfg = config.load({"scenes": ["work"], "schedule": {}})
        utt, why = daemon.decide(Event("feishu", "产品群", "@你 帮我看下这个", bot=False), cfg, dry=True)
        self.assertTrue(utt and "点你名" in utt["text"], why)

    def test_api_mentions_read_like_popups(self):
        from bobao.sources.feishu import readable
        self.assertEqual(readable("@_all 开会"), "@所有人 开会")
        self.assertIn("@你", readable('<at user_id="ou_1">小王</at> 看下', me="小王"))
        cfg = config.load({"scenes": ["work"], "schedule": {}})
        utt, why = daemon.decide(Event("feishu", "产品群", readable("@_all 下午开会"), bot=False), cfg, dry=True)
        self.assertTrue(utt and "所有人" in utt["text"], why)

    def test_combined_scenes_keep_what_one_turns_off(self):
        cfg = config.load({"scenes": ["work", "business", "dev"], "schedule": {}})
        self.assertIsNot(cfg["types"].get("收款", {}).get("enabled"), False)
        self.assertIs(config.load({"scenes": ["dev"]})["types"]["收款"]["enabled"], False)


class Recommend(unittest.TestCase):
    def test_bundle_voices_exist_and_text_mentions_scenes(self):
        from bobao import __main__ as m
        rec = m.recommendations()
        names = {v["name"] for v in m.catalog()}
        for picks in rec["scenes"].values():
            self.assertTrue(set(picks) <= names, picks)
        text = m.recommend_text(config.load({"scenes": ["work"]}), {"scenes": ["work"]})
        self.assertIn("招牌搭配", text)
        self.assertIn("若溪", text)
        self.assertIn("喊话", text)
