"""macOS notifications from any app (WeChat, DingTalk, Mail...), read from the spool the
helper app writes (helper/bobao-notify.swift). Only apps listed in
sources.notifications.apps are written there, and only title and preview text exist:
apps hide the rest. No app is hooked or automated, so no account is put at risk.

A Feishu popup for a group that the Feishu source reads only nudges that source to
check now; the full card is read through the API.
"""

import json
import os

from .. import paths
from ..events import Event

LARK_APPS = ("com.electron.lark", "feishu")


class Spool:
    def __init__(self):
        try:
            self.offset = os.path.getsize(paths.SPOOL)   # start at the end: no backlog
        except OSError:
            self.offset = 0

    def read(self):
        """New spool lines as dicts."""
        try:
            size = os.path.getsize(paths.SPOOL)
        except OSError:
            return []
        if size < self.offset:   # truncated by the helper
            self.offset = 0
        with open(paths.SPOOL, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        end = data.rfind(b"\n") + 1
        self.offset += end
        out = []
        for line in data[:end].splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out


def is_lark(app):
    return any(a in app.lower() for a in LARK_APPS)


def to_event(n):
    text = "，".join(x for x in (n.get("subtitle"), n.get("body")) if x)
    return Event("notifications", n.get("app", ""), n.get("title", ""), text, bot=None, time=n.get("time"))
