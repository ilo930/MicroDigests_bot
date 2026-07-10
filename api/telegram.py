"""
Vercel serverless webhook for MicroDigests_bot's interactive replies.

Telegram POSTs each incoming message here; we hand the text to reply_core and
send the reply back. Deployed at  https://<project>.vercel.app/api/telegram

Env vars to set in Vercel:
  TELEGRAM_BOT_TOKEN  (same bot as the digest)
  GROQ_API_KEY        (same key)
  WEBHOOK_SECRET      (any random string; also passed when registering the webhook)
"""

import os
import sys
import json
from http.server import BaseHTTPRequestHandler

# Make the repo-root modules importable from inside /api.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import reply_core

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SECRET = os.environ.get("WEBHOOK_SECRET", "")


def send(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=20)
    except Exception as e:
        print(f"[webhook] send failed: {e}")


class handler(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self._ok()  # health check

    def do_POST(self):
        if SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"forbidden")
            return
        try:
            length = int(self.headers.get("content-length", 0))
            update = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._ok()
            return

        msg = update.get("message") or update.get("edited_message") or {}
        chat = (msg.get("chat") or {}).get("id")
        text = msg.get("text", "")
        if chat and text:
            try:
                for reply in reply_core.handle_text(text):
                    send(chat, reply)
            except Exception as e:
                print(f"[webhook] handler error: {e}")
                send(chat, "Something went wrong — send <b>help</b> for commands.")
        self._ok()
