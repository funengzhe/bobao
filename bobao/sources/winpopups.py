"""Windows: Feishu's message popups, as a nudge for the Feishu source.

Feishu on Windows draws its own popup window; through Windows UI Automation it shows who
or which group a message is from, but not the message. So the popup only says "check now":
each one is written to the spool like a macOS popup ({"app": "feishu", "nudge": ...}), and
the Feishu source, read as yourself (lark-cli auth login), fetches the message through the
API within seconds instead of at the next minute's check.

WeChat 4 on Windows shows no popup and draws its window itself, so it cannot be read here.
"""

import json
import os
import subprocess
import threading
import time

from .. import paths, system
from ..log import log

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winpopups.ps1")


def line_to_spool(line, now=None):
    """'POPUP\\t产品群' -> the spool entry, or None."""
    kind, _, title = line.rstrip("\r\n").partition("\t")
    if kind != "POPUP":
        return None
    return {"app": "feishu", "title": title, "nudge": True, "anyGroup": True, "time": now or time.time()}


class Watcher:
    def __init__(self):
        self.started = False

    def ensure(self):
        if not self.started and system.WINDOWS:
            self.started = True
            threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                     "-File", SCRIPT], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL, creationflags=system.NO_WINDOW)
            log("开始留意飞书弹窗")
            for raw in proc.stdout:
                entry = line_to_spool(raw.decode("utf-8", "replace"))
                if entry:
                    paths.ensure()
                    with open(paths.SPOOL, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            proc.wait()
            log(f"飞书弹窗监视退出（{proc.returncode}），10 秒后重启")
            time.sleep(10)
