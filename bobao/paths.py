"""Where Bobao keeps its files. Everything lives under one folder, ~/.bobao by default
(set BOBAO_HOME to move it), so a background agent can read it and a reset is one rm."""

import os

HOME = os.path.expanduser(os.environ.get("BOBAO_HOME", "~/.bobao"))
CONFIG = os.path.join(HOME, "config.json")
STATE = os.path.join(HOME, "state.json")          # per-source cursors
LOG = os.path.join(HOME, "bobao.log")
CLIPS = os.path.join(HOME, "clips")               # recorded phrases + index.json
SOUNDS = os.path.join(HOME, "sounds")             # opening sound effects
PENDING = os.path.join(HOME, "pending.txt")       # sentences spoken without a recording
SPOOL = os.path.join(HOME, "notifications.jsonl") # written by the notification helper
RECORDING = os.path.join(HOME, "recording.json")  # RooYun requestIds, so a retry never pays twice
APP = os.path.join(HOME, "app")                   # installed copy the agent runs from
LAST_WAV = os.path.join(HOME, "last.wav")
PID = os.path.join(HOME, "bobao.pid")             # the running background process (Windows)

PACKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs")


def ensure():
    os.makedirs(CLIPS, exist_ok=True)
    os.makedirs(SOUNDS, exist_ok=True)
