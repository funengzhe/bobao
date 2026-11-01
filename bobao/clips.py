"""The library of recorded phrases, per voice, and stitching them into one sentence.

~/.bobao/clips/index.json maps "voice|emotion" -> {phrase without spaces: file}. All
clips are 24 kHz mono 16-bit WAV with the silence at both ends cut, so they can be
joined byte for byte with short, even gaps.
"""

import array
import hashlib
import json
import os
import re
import subprocess
import wave

from . import paths
from .numbers import NUMBER_CHARS, spoken_digits

INDEX = os.path.join(paths.CLIPS, "index.json")


def key(text):
    return re.sub(r"\s+", "", text)


def load():
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(index):
    paths.ensure()
    with open(INDEX + ".tmp", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    os.replace(INDEX + ".tmp", INDEX)


def has(index, vkey, text):
    return key(text) in index.get(vkey, {})


def find(text, phrases):
    """Clips for one sentence in one voice: a list of parts (one per "，"), each a list of
    (file, is a number word); None if anything has no recording. A sentence recorded
    whole wins; otherwise each part is matched whole or by longest pieces."""
    whole = key(text)
    if whole in phrases:
        return [[(phrases[whole], False)]]
    parts = []
    for part in re.split(r"[，,]", text):
        part = key(spoken_digits(part))
        if not part:
            continue
        files, i = [], 0
        while i < len(part):
            hit = max((k for k in phrases if part.startswith(k, i)), key=len, default=None)
            if not hit:
                return None
            files.append((phrases[hit], all(c in NUMBER_CHARS for c in hit)))
            i += len(hit)
        parts.append(files)
    return parts or None


def for_segments(segments, index):
    """[(voice, text)] -> list of parts across all segments, or None if any is missing."""
    from .config import voice_key
    out = []
    for voice, text in segments:
        phrases = {k: os.path.join(paths.CLIPS, f) for k, f in index.get(voice_key(voice), {}).items()}
        found = find(text, phrases)
        if not found:
            return None
        if out:
            found[0] = [(f, n, 0.35) for f, n in found[0]]   # a breath before the second voice
        out += found
    return out


def stitch(parts, path):
    """Joins clips: 250 ms at a comma, 40 ms between words, 10 ms inside a number."""
    out = None
    for pi, files in enumerate(parts):
        for fi, item in enumerate(files):
            f, numeric = item[0], item[1]
            with wave.open(f) as w:
                if out is None:
                    out = wave.open(path, "wb")
                    out.setparams(w.getparams())
                    rate, width = w.getframerate(), w.getsampwidth() * w.getnchannels()
                if len(item) > 2 and fi == 0:
                    gap = item[2]
                elif pi == fi == 0:
                    gap = 0
                elif fi == 0:
                    gap = 0.25
                else:
                    gap = 0.01 if numeric and files[fi - 1][1] else 0.04
                out.writeframes(b"\0" * int(rate * gap) * width)
                out.writeframes(w.readframes(w.getnframes()))
    if out:
        out.close()


def trim(path, threshold=0.012, keep=0.02):
    """Cuts leading and trailing silence in place (16-bit mono)."""
    with wave.open(path) as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    samples = array.array("h", frames)
    limit = int(32767 * threshold)
    loud = [i for i in range(0, len(samples), 48) if abs(samples[i]) > limit]
    if not loud:
        return
    pad = int(params.framerate * keep)
    start, end = max(0, loud[0] - pad), min(len(samples), loud[-1] + 48 + pad * 2)
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(samples[start:end].tobytes())


def add(index, vkey, text, src):
    """Converts any audio file (mp3, wav, aiff...) to a library clip for `text`."""
    paths.ensure()
    name = hashlib.sha1(f"{vkey}|{key(text)}".encode()).hexdigest()[:16] + ".wav"
    dest = os.path.join(paths.CLIPS, name)
    subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", src, dest],
                   check=True, capture_output=True)
    trim(dest)
    index.setdefault(vkey, {})[key(text)] = name
    return dest


def missing(plan, index):
    """{voice key: [texts]} still to record for a plan (see compose.plan)."""
    from .numbers import vocabulary
    out = {}
    for vkey, e in plan.items():
        texts = list(e["phrases"]) + (vocabulary() if e["numbers"] else [])
        todo = [t for t in texts if not has(index, vkey, t)]
        if todo:
            out[vkey] = todo
    return out
