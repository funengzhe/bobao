"""Amounts as spoken Chinese, and the number words a voice needs recorded to say any
amount. Numbers are stitched from whole words ("三十九", "两百") rather than single
digits, so they sound like one word."""

import re

DIGITS = "零一二三四五六七八九"
NUMBER_CHARS = DIGITS + "两十百千万点"


def cn_number(s):
    """'39' -> '三十九', '5.35' -> '五点三五', '105' -> '一百零五', '2' -> '两' (below 100 million)."""
    whole, _, frac = s.partition(".")
    n = int(whole or 0)

    def section(n):  # 0 < n < 10000
        out, zero = "", False
        for value, unit in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
            d = n // value % 10
            if d:
                digit = "两" if d == 2 and unit in ("千", "百") else DIGITS[d]   # 两百 / 两千, as people say it
                out += ("零" if zero and out else "") + digit + unit
                zero = False
            else:
                zero = True
        return out

    if n == 0:
        text = "零"
    elif n < 10000:
        text = section(n)
    else:
        high, low = divmod(n, 10000)
        text = section(high) + "万" + (("零" if low < 1000 else "") + section(low) if low else "")
    if text.startswith("一十"):
        text = text[1:]
    if text == "二" and not frac or text.startswith("二万"):   # 两美元, 两万
        text = "两" + text[1:]
    return text + ("点" + "".join(DIGITS[int(d)] for d in frac) if frac else "")


def spoken_digits(text):
    return re.sub(r"\d+(?:\.\d+)?", lambda m: cn_number(m.group(0)), text)


def vocabulary():
    """Every number word to record: digits, 十一–九十九, 一百–九百, 一千–九千, 万, 点."""
    words = list(DIGITS) + ["两", "十", "万", "点"]
    words += [cn_number(str(n)) for n in range(11, 100)]
    words += [cn_number(str(n * 100)) for n in range(1, 10)]
    words += [cn_number(str(n * 1000)) for n in range(1, 10)]
    return list(dict.fromkeys(words))


def money(text):
    """'9.90 USD' -> '9.9 美元', '¥99.00' -> '99 元', '$5' -> '5 美元'."""
    def num(s):
        s = s.replace(",", "")
        return s.rstrip("0").rstrip(".") if "." in s else s
    text = re.sub(r"([\d,]+(?:\.\d+)?)\s*(USDT|USD|CNY|RMB|美元|元)",
                  lambda m: num(m.group(1)) + {"USDT": " USDT", "USD": " 美元", "美元": " 美元"}.get(m.group(2), " 元"), text)
    text = re.sub(r"[¥￥]\s*([\d,]+(?:\.\d+)?)", lambda m: num(m.group(1)) + " 元", text)
    text = re.sub(r"\$\s*([\d,]+(?:\.\d+)?)", lambda m: num(m.group(1)) + " 美元", text)
    return text


UNITS = ["元", "美元", "USDT"]


def amount_of(text):
    m = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    return float(m.group(0).replace(",", "")) if m else None
