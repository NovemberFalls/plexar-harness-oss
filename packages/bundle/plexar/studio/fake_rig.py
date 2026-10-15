"""Fake Plexar rig for CI: an OpenAI-compatible server that answers every chat with a fixed reply.

Stdlib only. Lets a client run the real harness end to end with no GPU and no network:

    python fake_rig.py --port 8799 &
    PLEXAR_RIG_URL=http://127.0.0.1:8799 PLEXAR_HARNESS_KEY=fake plexar-harness acp

`GET /v1/models` lists the model; `POST /v1/chat/completions` answers with FAKE_REPLY (default
`PLEXAR_OK`), streamed as server-sent events when the request asks for `stream`. Any key is accepted
except `rejected`, which gets 401 so the key_rejected path can be tested too.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get("PLEXAR_MODEL", "Qwen/Qwen3.6-35B-A3B")
REPLY = os.environ.get("FAKE_REPLY", "PLEXAR_OK")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def _authorized(self) -> bool:
        if self.headers.get("Authorization", "") == "Bearer rejected":
            self._json(401, {"message": "Missing or invalid API key.", "type": "invalid_request_error", "code": "unauthorized"})
            return False
        return True

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "fake-rig"}]})
        else:
            self._json(404, {"message": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"message": "not found"})
            return
        created = int(time.time())
        usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        if not body.get("stream"):
            self._json(200, {
                "id": "chatcmpl-fake", "object": "chat.completion", "created": created, "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY}, "finish_reason": "stop"}],
                "usage": usage,
            })
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": created, "model": MODEL}
        chunks = [
            {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": REPLY}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {**base, "choices": [], "usage": usage},
        ]
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8799)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fake rig on http://127.0.0.1:{args.port} serving {MODEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
