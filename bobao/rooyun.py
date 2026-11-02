"""Recording phrases with RooYun (如云) voices, through RooYun's open API.

Login is the device flow: `bobao rooyun login` opens a page where you click 授权, and the
token is saved to ~/.rooyun/credentials.json (0600), the same file RooYun's own tools use.
ROOYUN_API_TOKEN overrides it. The token is only ever sent to RooYun, never printed.

Every recording run is quoted first and needs your yes. Each phrase gets a requestId
that is saved before submitting, so a rerun after a crash or a network drop never pays
twice for the same phrase.
"""

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from . import clips, paths
from .config import read_json

CRED_DIR = os.path.expanduser("~/.rooyun")
CRED_FILE = os.path.join(CRED_DIR, "credentials.json")
SUBMIT_GAP = 6.5   # RooYun allows 10 generation submits a minute per token


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(f"{code or status}: {message}")
        self.status, self.code = status, code


def token(base):
    t = os.environ.get("ROOYUN_API_TOKEN", "").strip()
    if t:
        return t
    entry = ((read_json(CRED_FILE, {}) or {}).get("tokens") or {}).get(base) or {}
    return (entry.get("token") or "").strip() or None


def _http(method, url, body=None, auth=None, redirect=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("accept", "application/json")
    if data is not None:
        req.add_header("content-type", "application/json")
    if auth:
        req.add_header("authorization", f"Bearer {auth}")
    opener = urllib.request.build_opener() if redirect else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.tok = token(self.base)
        if not self.tok:
            raise SystemExit("还没有登录 RooYun（如云）。运行：bobao rooyun login")

    def call(self, method, path, body=None):
        for attempt in range(6):
            status, headers, raw = _http(method, f"{self.base}/api/v1{path}", body, self.tok)
            try:
                env = json.loads(raw or b"{}")
            except ValueError:
                env = {}
            if status == 429 or status >= 500:
                time.sleep(min(60, 10 * (attempt + 1)))
                continue
            if not env.get("ok"):
                err = env.get("error") or {}
                raise ApiError(status, err.get("code"), err.get("message") or raw[:200].decode("utf-8", "replace"))
            return env
        raise ApiError(status, "retry_exhausted", "RooYun（如云）暂时不可用，稍后再试")

    def me(self):
        return self.call("GET", "/me")["data"]

    def voices(self):
        return self.call("GET", "/voices")["data"]["voices"]

    def models(self):
        return self.call("GET", "/models?capability=t2a")["data"]["models"]

    def model_for(self, voice, cfg):
        """The t2a model for a voice: RooYun's system voices use cfg rooyun.model, your own
        cloned or designed voices (kind "user") use RooYun's self-hosted model."""
        models = self.models()
        own = voice.get("kind") == "user"
        want = (cfg["rooyun"].get("ownVoiceModel") or "IndexTTS") if own else cfg["rooyun"].get("model", "speech-2.8-hd")
        for m in models:
            if want in m["name"]:
                return m["id"], own
        raise SystemExit(f"RooYun（如云）上找不到配音模型「{want}」")

    def precheck(self, items):
        total, out = 0.0, None
        for i in range(0, len(items), 100):
            d = self.call("POST", "/generations/precheck", {"items": items[i:i + 100]})["data"]
            if not all(x.get("priced") for x in d["items"]):
                raise SystemExit("有句子报不出价格，先不录")
            total += d["total"]
            out = d
        return round(total, 2), out["available"] if out else 0

    def generate(self, request_id, model, params):
        return self.call("POST", "/generations", {"requestId": request_id, "model": model,
                                                  "capability": "t2a", "params": params})["data"]["taskId"]

    def task(self, task_id):
        return self.call("GET", f"/generations/{task_id}")["data"]

    def download(self, asset_id, dest):
        status, headers, raw = _http("GET", f"{self.base}/api/v1/assets/{asset_id}/download", auth=self.tok, redirect=False)
        if status not in (301, 302, 303, 307):
            raise ApiError(status, "download", raw[:200].decode("utf-8", "replace"))
        status, _, raw = _http("GET", headers["location"])   # a signed URL: no token sent along
        if status != 200:
            raise ApiError(status, "download", "下载失败")
        with open(dest, "wb") as f:
            f.write(raw)


def login(base, out=print):
    """Device login: prints a link, waits until you click 授权 (up to 10 minutes)."""
    base = base.rstrip("/")
    status, _, raw = _http("POST", f"{base}/api/connect/code", {"clientName": "Bobao 定制播报"})
    env = json.loads(raw or b"{}")
    if not env.get("ok"):
        raise SystemExit(f"申请授权失败：{(env.get('error') or {}).get('message') or status}")
    d = env["data"]
    url = d["verificationUrl"]
    out(f"请在浏览器里登录 RooYun（如云）并点「授权」：{url}")
    if url.startswith(base):
        subprocess.run(["/usr/bin/open", url])
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(max(3, d.get("intervalSec", 3)))
        status, _, raw = _http("POST", f"{base}/api/connect/poll", {"deviceCode": d["deviceCode"]})
        if status == 429:
            continue
        env = json.loads(raw or b"{}")
        if not env.get("ok"):
            raise SystemExit(f"授权失败：{(env.get('error') or {}).get('message') or status}，请重新运行 bobao rooyun login")
        if env["data"].get("status") == "approved":
            all_ = read_json(CRED_FILE, {}) or {}
            tokens = dict(all_.get("tokens") or {})
            tokens[base] = {"token": env["data"]["token"], "name": env["data"].get("tokenName"),
                            "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
            os.makedirs(CRED_DIR, mode=0o700, exist_ok=True)
            fd = os.open(CRED_FILE + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"version": 1, "tokens": tokens}, f, indent=2)
            os.replace(CRED_FILE + ".tmp", CRED_FILE)
            out("已登录 RooYun（如云），令牌保存在 ~/.rooyun/credentials.json")
            return
    raise SystemExit("等了 10 分钟还没授权，请重新运行 bobao rooyun login")


# ---- recording --------------------------------------------------------------

def jobs_for(todo, client, cfg, voices_meta):
    """[(voice key, voice, text, model, params)] for {voice key: [texts]}."""
    from .compose import plan
    voices = {k: e["voice"] for k, e in plan(cfg).items()}
    out = []
    for vkey, texts in todo.items():
        v = dict(voices[vkey], kind=voices_meta.get(voices[vkey]["voice"], {}).get("kind"))
        model, own = client.model_for(v, cfg)
        for text in texts:
            params = {"text": text, "voiceId": v["voice"]}
            if v.get("emotion") and not own:
                params["emotion"] = v["emotion"]
            out.append((vkey, v, text, model, params))
    return out


def quote(client, jobs):
    return client.precheck([{"model": m, "capability": "t2a", "params": {"text": p["text"]}} for _, _, _, m, p in jobs])


def record(client, jobs, out=print):
    """Submits, waits for and imports every job. Safe to rerun: saved requestIds are reused."""
    state = read_json(paths.RECORDING, {}) or {}

    def save():
        with open(paths.RECORDING + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(paths.RECORDING + ".tmp", paths.RECORDING)

    keys = []
    for n, (vkey, v, text, model, params) in enumerate(jobs, 1):
        k = f"{vkey}|{clips.key(text)}"
        keys.append((k, vkey, text))
        e = state.setdefault(k, {})
        if e.get("taskId"):
            continue
        e.setdefault("requestId", str(uuid.uuid4()))
        save()
        try:
            e["taskId"] = client.generate(e["requestId"], model, params)
        except ApiError as err:
            if err.status == 402:
                save()
                raise SystemExit("RooYun（如云）积分不够了，充值后重新运行同一条命令，已提交的不会重复扣费")
            out(f"  提交失败，下次重跑会再试：{text}（{err}）")
            continue
        save()
        out(f"  已提交 {n}/{len(jobs)}：{text}")
        time.sleep(SUBMIT_GAP)

    index, done, failed = clips.load(), 0, 0
    for k, vkey, text in keys:
        e = state.get(k) or {}
        if not e.get("taskId") or clips.has(index, vkey, text):
            continue
        for _ in range(200):
            t = client.task(e["taskId"])
            if t.get("status") in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(3)
        if t.get("status") != "succeeded" or not t.get("assetId"):
            failed += 1
            out(f"  没录成：{text}（{t.get('status')}），下次重跑会换个新任务再录")
            state.pop(k, None)   # a failed task returns itself for the same requestId; start fresh
            save()
            continue
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp3")
            client.download(t["assetId"], src)
            clips.add(index, vkey, text, src)
        clips.save(index)
        e["done"] = True
        save()
        done += 1
    return done, failed
