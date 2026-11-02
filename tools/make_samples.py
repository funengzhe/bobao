#!/usr/bin/env python3
"""Records the listening page's audio with RooYun: the scene lines (docs/samples.json) in the
main voice, the install greeting, and one self-introduction per voice in packs/voices.json.
Only what is missing is recorded.

    python3 tools/make_samples.py            quote what is missing (free)
    python3 tools/make_samples.py --record   record it (asks first)

requestIds live in docs/.samples-tasks.json (not committed), so a rerun never pays twice.
"""

import json
import os
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOBAO_HOME", os.path.join(ROOT, ".bobao-samples"))

from bobao import config, rooyun  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
TASKS = os.path.join(DOCS, ".samples-tasks.json")


def jobs():
    s = json.load(open(os.path.join(DOCS, "samples.json"), encoding="utf-8"))
    out = [(e["file"], s["main"]["id"], e["text"]) for e in s["scenes"]]
    out.append((s["welcome"]["file"], s["main"]["id"], s["welcome"]["text"]))
    for v in json.load(open(os.path.join(ROOT, "packs", "voices.json"), encoding="utf-8"))["voices"]:
        out.append((v["intro"], v["id"], s["intro"].replace("{名字}", v["name"])))
    return [j for j in out if not os.path.exists(os.path.join(DOCS, j[0]))]


def main():
    todo = jobs()
    if not todo:
        print("试听音频都已生成")
        return
    c = rooyun.Client("https://www.rooyun.com")
    model = c.model_for({"voice": "", "kind": "system"}, config.load({}))[0]
    price, available = c.precheck([{"model": model, "capability": "t2a", "params": {"text": t}} for _, _, t in todo])
    print(f"要生成 {len(todo)} 段，约 {price} 积分，可用 {round(available, 2)}")
    if "--record" not in sys.argv:
        return
    if input("开始吗？[y/N] ").strip().lower() not in ("y", "yes"):
        sys.exit("没有生成")
    state = json.load(open(TASKS)) if os.path.exists(TASKS) else {}

    def save():
        json.dump(state, open(TASKS, "w"), ensure_ascii=False, indent=1)

    for path, voice, text in todo:
        s = state.setdefault(path, {})
        if s.get("taskId"):
            continue
        s.setdefault("requestId", str(uuid.uuid4()))
        save()
        s["taskId"] = c.generate(s["requestId"], model, {"text": text, "voiceId": voice})
        save()
        print("已提交", path, flush=True)
        time.sleep(rooyun.SUBMIT_GAP)
    for path, _, _ in todo:
        for _ in range(200):
            t = c.task(state[path]["taskId"])
            if t.get("status") in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(3)
        if t.get("status") == "succeeded":
            c.download(t["assetId"], os.path.join(DOCS, path))
        else:
            print("没成功，重跑会换一个 requestId 重录：", path)
            state.pop(path, None)
            save()


if __name__ == "__main__":
    main()
