"""Builds the WorkBuddy skill package from this repo: dist/bobao-workbuddy.zip.

    python3 tools/workbuddy.py [--author 名字] [--examples dist/workbuddy-examples.json]

author: who publishes it (default funengzhe). examples: {"zh": [...], "en": [...]}, the
"试试这样问我" lines; your own playful ones can stay in a local file outside git.

SKILL.md is AGENTS.md with WorkBuddy's frontmatter on top, and the code ships inside the
package, so installing needs no GitHub. WorkBuddy allows only skill/folder/file, so every
file sits directly in scripts/ with its path in the name (bobao~sources~webhook.py), and
scripts/unpack.py puts them back into ~/bobao. Only the download steps differ from
AGENTS.md: unpack from the skill folder instead of git clone. If AGENTS.md changes there, the build
stops instead of shipping steps that point nowhere. Upload the zip on open.workbuddy.cn.
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bobao import __version__  # noqa: E402

SHIP = ("AGENTS.md", "GUIDE.md", "LICENSE", "README.md", "assets/", "bin/", "bobao/", "helper/", "packs/")
COPY = 'python3 "<本技能目录>/scripts/unpack.py"'
UNPACK = '''"""Puts Bobao's files back into ~/bobao (or the folder given): a~b~c.py -> a/b/c.py."""
import os
import shutil
import stat
import sys

here = os.path.dirname(os.path.abspath(__file__))
dest = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/bobao"))
for name in os.listdir(here):
    if name == os.path.basename(__file__) or name.startswith("."):
        continue
    target = os.path.join(dest, *name.split("~"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(os.path.join(here, name), target)
run = os.path.join(dest, "bin", "bobao")
os.chmod(run, os.stat(run).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print("Bobao 已放到", dest)
'''

FRONT = f"""---
name: bobao
display_name: Bobao 定制播报
display_name_en: Bobao Voice Alerts
description: 在 macOS（Windows 测试版）上装好并配置 Bobao：把用户在意的消息（群里 @你、到账、构建失败、外卖、日程、定时提醒、智能体干完活）用他喜欢的声音、他想听的话念出来。当用户说「帮我装上 Bobao」「消息来了念给我听」「到账了喊我一声」「你干完活叫我一声」「换个声音」「改一下播报的说法」「加个下班提醒」，或提到 Bobao、语音播报、消息播报时使用。生成好听的声音前必须先报价、等用户同意。
description_zh: 把你在意的消息，用你喜欢的声音念出来。读电脑弹窗、飞书、Webhook 和定时提醒，22 个声音可选，消息只在你自己的电脑上处理。
description_en: Reads the messages you care about aloud, in a voice you pick. Desktop popups, Feishu, webhooks and timed reminders; messages stay on your own computer.
{{examples}}version: {__version__}
author: {{author}}
---

> 本技能自带 Bobao 的全部代码，在本技能目录的 `scripts/` 里（文件名里的 `~` 是目录分隔），「2. 下载」会把它们还原到 `~/bobao`；不需要访问 GitHub。
> 更新：技能市场更新本技能后，重新做一遍「2. 下载」再运行 `~/bobao/bin/bobao install --quiet`，设置和录好的声音在 `~/.bobao`，不受影响。

"""

SWAPS = [
    ("""```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

已经有了就更新到最新（设置和录音在 `~/.bobao`，不受影响）：

```bash
git -C ~/bobao fetch origin && git -C ~/bobao reset --hard origin/main
```""", f"""从本技能目录还原到 `~/bobao`（已经有了也这样做，就是更新；设置和录音在 `~/.bobao`，不受影响）：

```bash
{COPY}
```

检查：`~/bobao/bin/bobao --help` 能运行。"""),
    ("""下载：`git clone https://github.com/funengzhe/bobao "%USERPROFILE%\\bobao"`。""",
     f"""下载：`py -3 "<本技能目录>\\scripts\\unpack.py"`（还原到 `%USERPROFILE%\\bobao`）。"""),
    ("用户把这个仓库交给你，", "用户装了这个技能，"),
]


EXAMPLES = {
    "zh": ["帮我装上 Bobao，到账了就念金额，超过一千加一句「大单来啦」", "你干完活叫我一声，就说「Claude 交作业啦，过来看看」",
           "Claude 有问题要问我、等我批准的时候也告诉我", "工作日六点提醒我下班，晚上十一点以后别出声",
           "放几个好听的声音给我听听，我挑一个"],
    "en": ["Install Bobao and read out every payment, with a cheer for orders over 1,000",
           "Call me when you finish a task: \"Claude's homework is done, come take a look\"",
           "Tell me when Claude has a question or needs my approval", "Remind me to leave at six on workdays, and stay quiet after 11 pm",
           "Play me a few voices so I can pick one"],
}


def examples_yaml(ex):
    return "".join(f"examples_{k}:\n" + "".join(f"  - {json.dumps(x, ensure_ascii=False)}\n" for x in ex[k]) for k in ("zh", "en"))


def skill_md(author="funengzhe", examples=None):
    text = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    for old, new in SWAPS:
        if old not in text:
            raise SystemExit(f"AGENTS.md 变了，找不到要替换的这段，先改 tools/workbuddy.py：\n{old[:80]}")
        text = text.replace(old, new)
    return FRONT.replace("{author}", author).replace("{examples}", examples_yaml(examples or EXAMPLES)) + text


def shipped():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [f for f in files if f in SHIP or f.startswith(tuple(s for s in SHIP if s.endswith("/")))]


def build(out=None, author="funengzhe", examples=None):
    out = out or os.path.join(ROOT, "dist", "bobao-workbuddy.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bobao/SKILL.md", skill_md(author, examples))
        z.writestr("bobao/scripts/unpack.py", UNPACK)
        for f in shipped():
            assert "~" not in f, f
            with open(os.path.join(ROOT, f), "rb") as src:
                z.writestr("bobao/scripts/" + f.replace("/", "~"), src.read())
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    opt = lambda name, default=None: args[args.index(name) + 1] if name in args else default
    ex = opt("--examples")
    path = build(author=opt("--author", "funengzhe"), examples=json.load(open(ex, encoding="utf-8")) if ex else None)
    print(path, f"{os.path.getsize(path) / 1e6:.1f} MB")
    shutil.rmtree(os.path.join(ROOT, "tools", "__pycache__"), ignore_errors=True)
