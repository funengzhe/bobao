"""Opening sound effects, synthesized locally (free, no files to download).

    bobao sounds        writes them to ~/.bobao/sounds/<name>.wav

Rules and styles refer to them by name: coin, register, levelup, gift, bubble, doorbell,
chime, kalimba, drop, hum, siren, wahwah, beeps, oops, redalert. A macOS system sound name (Glass, Ping...) or a path
to your own file works too.
"""

import math
import os
import random
import struct
import wave

from . import paths

RATE = 24000


def silence(sec):
    return [0.0] * int(RATE * sec)


def tone(freq, sec, decay=6.0, partials=((1, 1.0),), attack=0.004, vibrato=0.0, glide_to=None):
    """A note with harmonic partials, a short attack and an exponential decay.
    glide_to slides the pitch linearly; vibrato is a depth in semitones at 6 Hz."""
    n, out, phase = int(RATE * sec), [], 0.0
    for i in range(n):
        t = i / RATE
        f = freq if glide_to is None else freq + (glide_to - freq) * t / sec
        if vibrato:
            f *= 2 ** (vibrato * math.sin(2 * math.pi * 6 * t) / 12)
        phase += 2 * math.pi * f / RATE
        env = min(1.0, t / attack) * math.exp(-decay * t)
        out.append(env * sum(a * math.sin(k * phase) for k, a in partials))
    return out


def noise(sec, decay=60.0):
    return [random.uniform(-1, 1) * math.exp(-decay * i / RATE) for i in range(int(RATE * sec))]


def mix(*tracks):
    """Overlays (start_sec, samples) pairs."""
    end = max(int(s * RATE) + len(x) for s, x in tracks)
    out = [0.0] * end
    for s, x in tracks:
        o = int(s * RATE)
        for i, v in enumerate(x):
            out[o + i] += v
    return out


BELL = ((1, 1.0), (2, 0.35), (3, 0.15), (4.2, 0.08))
MARIMBA = ((1, 1.0), (4, 0.25), (10, 0.05))
WARM = ((1, 1.0), (2, 0.12))
KALIMBA = ((1, 1.0), (5.4, 0.04))
SQUARE = tuple((k, 1 / k) for k in (1, 3, 5, 7))

SOUNDS = {
    # Payment: bright and rewarding.
    "支付·金币": ("coin", lambda: mix((0, tone(988, 0.12, 18, BELL)), (0.09, tone(1319, 0.7, 5, BELL)))),
    "支付·收银叮": ("register", lambda: mix((0, noise(0.05, 80)), (0.03, [v * 0.3 for v in noise(0.04, 90)]),
                                         (0.08, tone(2093, 0.9, 4, BELL)), (0.08, tone(1568, 0.9, 4.5, BELL)))),
    # Plan purchase: bigger than a payment, a rising sparkle.
    "套餐·升级": ("levelup", lambda: mix(*[(i * 0.07, tone(f, 0.5 if i < 3 else 0.9, 5, BELL))
                                           for i, f in enumerate((523, 659, 784, 1047))])),
    "套餐·礼包": ("gift", lambda: mix((0, [v * 0.6 for v in tone(500, 0.25, 3, ((1, 1.0), (2, 0.3)), glide_to=1000)]),
                                     *[(0.22 + i * 0.05, [v * 0.5 for v in tone(f, 0.6, 6, BELL)])
                                       for i, f in enumerate((1568, 2093, 2637, 3136))])),
    # Registration: light and friendly.
    "注册·气泡": ("bubble", lambda: mix((0, tone(420, 0.09, 25, ((1, 1.0),), glide_to=900)),
                                        (0.11, tone(600, 0.1, 22, ((1, 1.0),), glide_to=1200)))),
    "注册·门铃": ("doorbell", lambda: mix((0, tone(659, 0.5, 5, MARIMBA)), (0.28, tone(523, 0.8, 4, MARIMBA)))),
    # Soft: for reminders you hear many times a day (a third quieter, no strike).
    "提醒·风铃": ("chime", lambda: mix((0, tone(784, 1.2, 3.2, WARM, attack=0.02)),
                                       (0.22, tone(1047, 1.4, 3.0, WARM, attack=0.02))), 0.35),
    "提醒·拇指琴": ("kalimba", lambda: mix((0, tone(587, 0.9, 4.5, KALIMBA, attack=0.008)),
                                          (0.18, tone(880, 1.1, 4, KALIMBA, attack=0.008))), 0.38),
    "提醒·水滴": ("drop", lambda: tone(620, 0.35, 9, attack=0.01, glide_to=880), 0.32),
    "提醒·轻哼": ("hum", lambda: tone(523, 1.3, 2.6, WARM, attack=0.06), 0.3),
    # Alert: unhappy but cute, not a fire alarm.
    "告警·警报": ("siren", lambda: mix(*[(i * 0.22, [v * 0.45 for v in tone(880 if i % 2 == 0 else 660, 0.2, 2, SQUARE, 0.01)])
                                          for i in range(6)])),
    "告警·呜哇": ("wahwah", lambda: mix(*[(i * 0.32, [v * 0.6 for v in tone(f, 0.3 if i < 3 else 0.9, 2.5, SQUARE, 0.01,
                                                                           vibrato=0.4 if i == 3 else 0.0)])
                                          for i, f in enumerate((392, 370, 349, 330))])),
    "告警·滴滴滴": ("beeps", lambda: mix(*[(g * 0.45 + i * 0.1, [v * 0.5 for v in tone(1760, 0.07, 8, ((1, 1.0), (3, 0.2)), 0.003)])
                                            for g in range(2) for i in range(3)])),
    "告警·哎呀": ("oops", lambda: mix((0, tone(1200, 0.35, 3, ((1, 1.0), (2, 0.2)), glide_to=300, vibrato=1.2)),
                                       (0.4, [v * 0.7 for v in tone(220, 0.35, 6, MARIMBA)]))),
    "告警·红色警戒": ("redalert", lambda: mix(*[(i * 0.42, [v * 0.4 for v in tone(500, 0.38, 1.5, SQUARE, 0.01, glide_to=1100)])
                                               for i in range(2)])),
}


def write(path, samples, level=0.8):
    peak = max(abs(v) for v in samples) or 1.0
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        tail = samples + silence(0.05)
        w.writeframes(b"".join(struct.pack("<h", int(v / peak * level * 32767)) for v in tail))



def make_all():
    random.seed(7)
    paths.ensure()
    for slug, make, *level in SOUNDS.values():
        write(os.path.join(paths.SOUNDS, slug + ".wav"), make(), *level)
    return [slug for slug, *_ in SOUNDS.values()]
