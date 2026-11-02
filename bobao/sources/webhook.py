"""A local HTTP endpoint any system can post to, no chat app in between.

    curl -X POST http://127.0.0.1:8766/notify -H 'content-type: application/json' \\
         -d '{"title": "充值到账", "platform": "我的店", "fields": {"金额": "$19.9", "方式": "支付宝"}}'

Body: title (required), text, fields, channel, and optionally type / platform / name to
skip the rules. Add "dry": true to get back what would be said without playing it.
If sources.webhook.secret is set, send it as the X-Bobao-Secret header.
Listens on 127.0.0.1 only.
"""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..events import Event
from ..log import log


def serve(port, get_cfg, handle):
    """Runs the server in a thread. handle(event, dry) returns a dict for the reply."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(200, {"ok": True, "service": "bobao", "post": "/notify"})

        def do_POST(self):
            if self.path.rstrip("/") != "/notify":
                return self.reply(404, {"ok": False, "error": "POST /notify"})
            secret = get_cfg()["sources"]["webhook"].get("secret") or ""
            if secret and not hmac.compare_digest(self.headers.get("x-bobao-secret", ""), secret):
                return self.reply(401, {"ok": False, "error": "X-Bobao-Secret 不对"})
            try:
                n = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                assert isinstance(body, dict) and body.get("title")
            except Exception:
                return self.reply(400, {"ok": False, "error": "需要 JSON，且至少有 title"})
            fields = body.get("fields") if isinstance(body.get("fields"), dict) else {}
            ev = Event("webhook", str(body.get("channel") or ""), str(body["title"]), str(body.get("text") or ""),
                       {str(k): str(v) for k, v in fields.items()}, bot=True,
                       type=body.get("type"), platform=body.get("platform"), name=body.get("name"))
            self.reply(200, dict({"ok": True}, **handle(ev, bool(body.get("dry")))))

    server = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"Webhook 已开启：http://127.0.0.1:{port}/notify")
    return server
