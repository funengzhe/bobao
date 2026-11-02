"""Plays announcements one at a time: the sound effect, then the stitched recording, or
the Mac's own voice when the engine is "mac" or a sentence has no recording yet."""

import os
import queue
import subprocess
import threading

from . import clips, paths
from .log import log

SYSTEM_SOUNDS = "/System/Library/Sounds"


def sound_path(sound):
    if not sound:
        return None
    if os.sep in sound:
        return os.path.expanduser(sound)
    for p in (os.path.join(paths.SOUNDS, sound + ".wav"), os.path.join(SYSTEM_SOUNDS, sound + ".aiff")):
        if os.path.exists(p):
            return p
    return None


def note_pending(text):
    try:
        with open(paths.PENDING, encoding="utf-8") as f:
            if text in f.read().splitlines():
                return
    except FileNotFoundError:
        pass
    with open(paths.PENDING, "a", encoding="utf-8") as f:
        f.write(text + "\n")
    log(f"没有录音，先用 Mac 声音念（运行 bobao voice record 补录）：{text}")


def render_wav(utt, cfg, path):
    """Writes the recorded version of an utterance to `path`; False if not all recorded."""
    if cfg["engine"] != "rooyun":
        return False
    parts = clips.for_segments(utt["segments"], clips.load())
    if not parts:
        return False
    clips.stitch(parts, path)
    return True


def play(utt, cfg):
    s = sound_path(utt.get("sound"))
    if s:
        subprocess.run(["/usr/bin/afplay", s])
    if utt.get("file"):   # a ready-made recording (喊话, clips)
        subprocess.run(["/usr/bin/afplay", utt["file"]])
        return
    if render_wav(utt, cfg, paths.LAST_WAV):
        subprocess.run(["/usr/bin/afplay", paths.LAST_WAV])
        return
    text = "，".join(t for _, t in utt["segments"])
    if cfg["engine"] == "rooyun":
        note_pending(utt["text"])
    subprocess.run(["/usr/bin/say", "-v", cfg["macVoice"], "-r", str(cfg["rate"]), text])


class Speaker:
    def __init__(self):
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, utt, cfg):
        self.q.put((utt, cfg))

    def _run(self):
        while True:
            utt, cfg = self.q.get()
            try:
                play(utt, cfg)
            except Exception as e:
                log(f"播放失败: {e}")
