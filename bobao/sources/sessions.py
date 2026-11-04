"""Agents with no hook of their own (DeepSeek Harness and the like) still keep each
conversation in files. `bobao agent watch --name X --dir D` watches that folder: a turn
starts when a file there starts to grow, and it is done once nothing has been written for
`idle` seconds. With `done` (a regular expression) the end of the last file written must
also match it, for agents that write a clear end-of-turn mark: then a long silent tool run
is never taken for the end. Turns shorter than agents.minSeconds stay silent, as with
Claude Code. The agent that sets this up finds the folder itself (its own docs, or asking).
"""

import os
import re
import time

from ..events import Event

SCAN_EVERY = 2       # seconds between looks at the folders
MAX_FILES = 5000     # a folder bigger than this is looked at only in part
LONG, VERY_LONG = 10 * 60, 30 * 60


def snapshot(folder):
    """{path: (size, mtime)} for the files under a folder, newest first, at most MAX_FILES."""
    out = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[p] = (st.st_size, st.st_mtime)
            if len(out) >= MAX_FILES:
                return out
    return out


def tail(path, size=4096):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - size))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


class Watch:
    def __init__(self):
        self.files, self.turns, self.next = {}, {}, 0

    def check(self, cfg, handle, now=None):
        now = now or time.time()
        if now < self.next:
            return
        self.next = now + SCAN_EVERY
        agents = cfg.get("agents") or {}
        for w in agents.get("watch") or []:
            folder = os.path.expanduser(w.get("dir") or "")
            if not os.path.isdir(folder):
                continue
            files = snapshot(folder)
            before = self.files.get(folder)
            self.files[folder] = files
            if before is None:   # the first look only learns what is there
                continue
            grew = [p for p, v in files.items() if before.get(p) != v]
            turn = self.turns.get(folder)
            if grew:
                newest = max(grew, key=lambda p: files[p][1])
                if not turn:
                    turn = self.turns[folder] = {"start": now}
                turn.update(last=now, file=newest)
                continue
            if not turn or now - turn["last"] < w.get("idle", 15):
                continue
            if w.get("done") and not re.search(w["done"], tail(turn["file"])):
                continue   # quiet, but not at an end: a long tool run; the turn goes on
            del self.turns[folder]
            took = turn["last"] - turn["start"]
            if took < agents.get("minSeconds", 60):
                continue
            title = "智能体完成·很久" if took >= VERY_LONG else "智能体完成·久" if took >= LONG else "智能体完成"
            handle(Event("webhook", w.get("name") or "智能体", title, bot=True))
