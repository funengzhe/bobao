"""Builds the WorkBuddy skill package from this repo: dist/bobao-workbuddy.zip.

    python3 tools/workbuddy.py

SKILL.md is AGENTS.md with WorkBuddy's frontmatter on top, and the code ships inside the
package (scripts/bobao/), so installing needs no GitHub. Only the download steps differ:
copy from the skill folder instead of git clone. If AGENTS.md changes there, the build
stops instead of shipping steps that point nowhere. Upload the zip on open.workbuddy.cn.
"""

import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bobao import __version__  # noqa: E402

SHIP = ("AGENTS.md", "GUIDE.md", "LICENSE", "README.md", "assets/", "bin/", "bobao/", "helper/", "packs/")
COPY = 'mkdir -p ~/bobao && cp -R "<本技能目录>/scripts/bobao/." ~/bobao/'

FRONT = f"""---
name: bobao
display_name: Bobao 定制播报
display_name_en: Bobao Voice Alerts
description: 在 macOS（Windows 测试版）上装好并配置 Bobao：把用户在意的消息（群里 @你、到账、构建失败、外卖、日程、定时提醒、智能体干完活）用他喜欢的声音、他想听的话念出来。当用户说「帮我装上 Bobao」「消息来了念给我听」「到账了喊我一声」「你干完活叫我一声」「换个声音」「改一下播报的说法」「加个下班提醒」，或提到 Bobao、语音播报、消息播报时使用。生成好听的声音前必须先报价、等用户同意。
description_zh: 把你在意的消息，用你喜欢的声音念出来。读电脑弹窗、飞书、Webhook 和定时提醒，22 个声音可选，消息只在你自己的电脑上处理。
description_en: Reads the messages you care about aloud, in a voice you pick. Desktop popups, Feishu, webhooks and timed reminders; messages stay on your own computer.
version: {__version__}
author: funengzhe
---

> 本技能自带 Bobao 的全部代码，在本技能目录的 `scripts/bobao/` 里。下面写的「仓库」就是这个文件夹；不需要访问 GitHub。
> 更新：技能市场更新本技能后，重新做一遍「2. 下载」再运行 `~/bobao/bin/bobao install --quiet`，设置和录好的声音在 `~/.bobao`，不受影响。

"""

SWAPS = [
    ("""```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

已经有了就更新到最新（设置和录音在 `~/.bobao`，不受影响）：

```bash
git -C ~/bobao fetch origin && git -C ~/bobao reset --hard origin/main
```""", f"""从本技能目录复制到 `~/bobao`（已经有了也这样做，就是更新；设置和录音在 `~/.bobao`，不受影响）：

```bash
{COPY}
```

检查：`~/bobao/bin/bobao --help` 能运行。"""),
    ("""下载：`git clone https://github.com/funengzhe/bobao "%USERPROFILE%\\bobao"`。""",
     f"""下载：在 Git Bash 里 `{COPY}`；PowerShell 里 `Copy-Item -Recurse -Force "<本技能目录>\\scripts\\bobao\\*" "$env:USERPROFILE\\bobao"`。"""),
    ("用户把这个仓库交给你，", "用户装了这个技能，"),
]


def skill_md():
    text = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    for old, new in SWAPS:
        if old not in text:
            raise SystemExit(f"AGENTS.md 变了，找不到要替换的这段，先改 tools/workbuddy.py：\n{old[:80]}")
        text = text.replace(old, new)
    return FRONT + text


def shipped():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [f for f in files if f in SHIP or f.startswith(tuple(s for s in SHIP if s.endswith("/")))]


def build(out=None):
    out = out or os.path.join(ROOT, "dist", "bobao-workbuddy.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bobao/SKILL.md", skill_md())
        for f in shipped():
            info = zipfile.ZipInfo.from_file(os.path.join(ROOT, f), f"bobao/scripts/bobao/{f}")
            with open(os.path.join(ROOT, f), "rb") as src:
                z.writestr(info, src.read(), zipfile.ZIP_DEFLATED)   # keeps bin/bobao executable
    return out


if __name__ == "__main__":
    path = build()
    print(path, f"{os.path.getsize(path) / 1e6:.1f} MB")
    shutil.rmtree(os.path.join(ROOT, "tools", "__pycache__"), ignore_errors=True)
