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

USER = {"rulePacks": ["bigmodel", "rooyun", "generic"],
        "platforms": {"Alpha": {"say": "Alpha", "channels": ["bm"]}, "Beta": {"say": "贝塔", "channels": ["ry"]}},
        "bigOrder": {"Alpha": 100, "Beta": 500}}


def cfg_for(style, **extra):
    return config.load(dict(USER, style=style, **extra))


def ev(title, channel="bm", **fields):
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
        self.assertEqual(self.kind(ev("[Beta] 套餐购买到账", "ry")), ("套餐", "Beta"))
        self.assertEqual(self.kind(ev("[Beta] 已恢复：接口", "ry")), ("恢复", "Beta"))

    def test_rules_stay_in_their_group(self):
        # 通道熔断 is a Beta alert; in the Alpha group only the generic net may catch it
        self.assertEqual(self.kind(ev("【警告】通道熔断", "ry")), ("告警", "Beta"))
        m, _ = classify(ev("【警告】通道熔断", "bm"), self.cfg)
        self.assertNotEqual(m.platform, "Beta")

    def test_skips(self):
        self.assertIsNone(self.kind(ev("【模拟】Alpha 充值到账 9.9 USD")))
        self.assertIsNone(self.kind(ev("[Beta] 本周注册全部来自测试账号", "ry")))
        self.assertIsNone(self.kind(ev("今天天气不错")))

    def test_people_are_not_read(self):
        m = {"content": "测试到账1元", "sender": {"sender_type": "user"}, "create_time": "2026-11-02 10:00"}
        self.assertIs(feishu.to_event("bm", m).bot, False)

    def test_amountless_payment_is_not_misread(self):
        utt, _ = daemon.decide(ev("[Beta] 充值到账", "ry"), self.cfg, dry=True)
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
        old = ev("[Beta] 经营日报", "ry")
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
            cards += [ev("[Beta] 套餐购买到账", "ry", 金额=f"¥{a}", 套餐=p) for a in ("39", "999") for p in ("会员·基础", "会员·创作者")]
            cards += [ev(t) for t in ("[Alpha] 新用户注册", "[Alpha] 经营日报", "支付通道熔断", "商品没有定价", "订单已取消", "[Alpha] 已恢复")]
            cards += [ev(t, "ry") for t in ("[Beta] 新用户注册", "通道熔断", "待审批：退款", "[Beta] 充值到账", "任务进程掉线")]
            cards += [ev("莫名其妙的故障")]
            for card in cards:
                for seed in range(25):
                    utt, why = daemon.decide(card, cfg, dry=True, rnd=random.Random(seed))
                    self.assertIsNotNone(utt, (style, card.title, why))
                    found = clips.for_segments(utt["segments"], lib)
                    self.assertIsNotNone(found, (style, utt["text"]))


if __name__ == "__main__":
    unittest.main()
