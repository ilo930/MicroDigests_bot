"""
poller.py — the interactive listener, run as a short-lived GitHub Actions job.

Instead of an always-on server, a scheduled workflow starts this every few
minutes; each run long-polls Telegram getUpdates for ~4.5 minutes, answers any
messages via reply_core, then exits. The next scheduled run picks up where this
left off (Telegram keeps unconfirmed updates for 24h), so nothing is missed —
replies just arrive within a couple of minutes rather than instantly.

Env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY  (already GitHub secrets for the digest)
     RUN_SECONDS (optional, default 270)
"""

import os
import time

import requests

import reply_core

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "270"))
LONG_POLL = 25


def send(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage",
                      json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=20)
    except Exception as e:
        print(f"[poller] send failed: {e}")


def main():
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")
    # getUpdates and a webhook are mutually exclusive; make sure none is set.
    try:
        requests.get(f"{API}/deleteWebhook", timeout=10)
    except Exception:
        pass

    offset = None
    deadline = time.time() + RUN_SECONDS
    print(f"[poller] polling for ~{RUN_SECONDS}s")
    while time.time() < deadline:
        try:
            params = {"timeout": LONG_POLL}
            if offset is not None:
                params["offset"] = offset
            data = requests.get(f"{API}/getUpdates", params=params,
                                timeout=LONG_POLL + 10).json()
            if not data.get("ok"):
                print(f"[poller] getUpdates not ok: {data}")
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                chat = (msg.get("chat") or {}).get("id")
                text = msg.get("text", "")
                if not (chat and text):
                    continue
                print(f"[poller] msg from {chat}: {text!r}")
                try:
                    for reply in reply_core.handle_text(text):
                        send(chat, reply)
                except Exception as e:
                    print(f"[poller] handler error: {e}")
                    send(chat, "Something went wrong — send <b>help</b> for commands.")
        except Exception as e:
            print(f"[poller] loop error: {e}")
            time.sleep(3)
    print("[poller] done")


if __name__ == "__main__":
    main()
