#!/usr/bin/env python3
"""smoke_test.py — the one command that answers "is the digest still alive?"

    python3 smoke_test.py

Six checks, cheapest first: the files are there, the code still loads, a digest
still renders offline, a news source answers, the channel actually received a
digest recently, and Telegram still knows the bot.

It never sends anything and never spends LLM credit. A check that cannot run
here (no token, no network) is reported as skipped — never as a pass.
Exit code 0 means nothing failed.
"""

import contextlib
import datetime
import io
import json
import os
import sys

# Set before news_bot is imported: it reads these switches at import time into
# module constants, so even a mistake below cannot post to the channel or call
# the LLM. This is a check, and a check must never have side effects.
os.environ["DRY_RUN"] = "1"
os.environ["MOCK_LLM"] = "1"

import requests

HERE = os.path.dirname(os.path.abspath(__file__))

# The digest's own record of its last real send, as published by the GitHub
# Actions run. The local copy is not used: this laptop's clone is usually
# behind, and it is the deployed bot we are asking about, not this folder.
LIVE_STATE_URL = ("https://raw.githubusercontent.com/ilo930/MicroDigests_bot/"
                  "main/state/latest_digest.json")
DIGEST_EVERY_DAYS = 3    # the cron in .github/workflows/news-bot.yml
STALE_AFTER_DAYS = 6     # one skipped run is tolerable; two means it is down

# A direct publisher feed rather than a Google News query: Google rate-limits
# repeated queries from one IP, which would turn this check red on a bot that
# is perfectly fine.
SAMPLE_FEED = "https://spaceflightnow.com/feed/"

CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@cosmic_spill")

REQUIRED_FILES = [
    "news_bot.py", "reply_core.py", "players.py", "poller.py", "watchlist.py",
    ".github/workflows/news-bot.yml", ".github/workflows/reply-bot.yml",
]


# ---------------------------------------------------------------------------
# The checks. Each returns (state, message): "ok", "fail" or "skip".
# ---------------------------------------------------------------------------

def check_files_present():
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(HERE, f))]
    if missing:
        return "fail", "Missing from the project: " + ", ".join(missing)
    return "ok", f"All {len(REQUIRED_FILES)} bot files are in place"


def check_code_loads():
    """Catches a syntax error or a broken import before the cron does."""
    try:
        import news_bot, reply_core, players, watchlist, poller  # noqa: F401
    except Exception as err:
        return "fail", f"The code no longer loads — {type(err).__name__}: {err}"
    return "ok", "Every part of the code still loads"


def check_digest_renders():
    """Builds a digest message from fake stories, with no news and no LLM.

    This is the part that would break silently after an edit: the bot would run,
    fetch, and send an empty or malformed message.
    """
    import news_bot as nb

    fake = {
        "space": [{
            "id": "smoke-1", "title": "A test rocket reached orbit", "link":
            "https://example.com/rocket", "source": "Smoke Test",
            "text": "Body text for the smoke test.",
        }],
        "minerals": [{
            "id": "smoke-2", "title": "A test mine opened", "link":
            "https://example.com/mine", "source": "Smoke Test",
            "text": "Body text for the smoke test.",
        }],
    }
    try:
        analyzed = nb.analyze_items(fake)
        n = 0
        for theme in nb.THEMES:
            for item in analyzed.get(theme, []):
                n += 1
                item["n"] = n
        messages = nb.build_theme_messages(analyzed, {}, "2026-01-01")
    except Exception as err:
        return "fail", f"Building a digest broke — {type(err).__name__}: {err}"

    if len(messages) != 2:
        return "fail", f"Expected 2 section messages, got {len(messages)}"
    body = "\n".join(text for _theme, text in messages)
    if "A test rocket reached orbit" not in body:
        return "fail", "The story never made it into the message"
    too_long = [t for _theme, t in messages if len(t) > nb.TELEGRAM_LIMIT]
    if too_long:
        return "fail", "A section came out longer than Telegram accepts"
    return "ok", f"A digest still renders — {len(messages)} sections, {len(body)} characters"


def check_cut_off_reply_is_survivable():
    """Guards the 2026-08-07 failure, when the AI's narration reply was cut off
    mid-JSON and every story went out as a bare headline and a link.

    Two defences have to hold: salvage what finished, and refuse to publish
    what did not.
    """
    import news_bot as nb

    cut_off = (
        '{\n  "items": [\n'
        '    {"i": 0, "topic": "launch", "country": "US", "headline": "A rocket flew",'
        ' "scifi_hook": "Whoa.", "eli5": "It went up.", "why": "It matters.",'
        ' "tickers": []},\n'
        '    {"i": 1, "topic": "mining", "country": "CA", "headline": "A mine opened",'
        ' "scifi_hook": "Rocks.", "eli5": "They dig.", "why": "Supply.",'
        ' "tickers": []},\n'
        '    {"i": 2, "topic": "quantum", "country": "US", "headline": "Qubits",'
        ' "scifi_hook": "The reply stops mid-w')
    with contextlib.redirect_stdout(io.StringIO()):
        salvaged = nb.extract_json(cut_off).get("items", [])
    if len(salvaged) != 2:
        return "fail", ("A cut-off reply should still yield the 2 finished stories, "
                        f"got {len(salvaged)}")

    bare = {"space": [{"title": "Headline only", "scifi_hook": "", "eli5": "", "why": ""}]}
    with contextlib.redirect_stdout(io.StringIO()):
        survivors = nb.drop_unnarrated(bare)
    if survivors:
        return "fail", "A story with no narration would still be sent to the channel"
    return "ok", "A cut-off AI reply is salvaged, and bare headlines never ship"


def check_news_source_answers():
    try:
        resp = requests.get(SAMPLE_FEED, headers={"User-Agent": "Mozilla/5.0"},
                            timeout=12)
    except requests.exceptions.RequestException as err:
        return "skip", f"No network here, news source not checked ({type(err).__name__})"
    if resp.status_code != 200:
        return "fail", f"Spaceflight Now answered {resp.status_code}, not 200"

    import feedparser
    entries = feedparser.parse(resp.content).entries
    if not entries:
        return "fail", "Spaceflight Now answered but the feed was empty"
    return "ok", f"News is flowing — Spaceflight Now returned {len(entries)} stories"


def check_channel_was_fed():
    try:
        resp = requests.get(LIVE_STATE_URL, timeout=12)
    except requests.exceptions.RequestException as err:
        return "skip", f"No network here, last digest not checked ({type(err).__name__})"
    if resp.status_code != 200:
        return "fail", f"Cannot read the bot's published state (HTTP {resp.status_code})"
    try:
        state = resp.json()
        sent_at = datetime.datetime.fromisoformat(state["generated_at"])
    except (ValueError, KeyError) as err:
        return "fail", f"The bot's published state is unreadable — {err}"

    days = (datetime.datetime.now(datetime.timezone.utc) - sent_at).days
    when = f"{state.get('date')} ({days} day{'s' if days != 1 else ''} ago), " \
           f"{len(state.get('items', []))} stories"
    if days > STALE_AFTER_DAYS:
        return "fail", f"The channel has had nothing since {when} — it runs every " \
                       f"{DIGEST_EVERY_DAYS} days"
    return "ok", f"The channel is being fed — last digest {when}"


def _bot_token():
    """Env first, then a local .env — which is gitignored and never printed."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        return token
    try:
        with open(os.path.join(HERE, ".env")) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key.strip() == "TELEGRAM_BOT_TOKEN":
                    return value.strip().strip("'\"")
    except OSError:
        pass
    return ""


def check_telegram():
    token = _bot_token()
    if not token:
        return "skip", "Telegram not checked — no bot token here (GitHub holds it)"
    api = f"https://api.telegram.org/bot{token}"
    try:
        me = requests.get(f"{api}/getMe", timeout=10).json()
        if not me.get("ok"):
            return "fail", "Telegram rejected the bot token"
        name = me["result"].get("username", "the bot")
        count = requests.get(f"{api}/getChatMemberCount",
                             params={"chat_id": CHANNEL}, timeout=10).json()
    except requests.exceptions.RequestException as err:
        return "skip", f"No network here, Telegram not checked ({type(err).__name__})"
    if not count.get("ok"):
        return "fail", f"@{name} is alive but cannot see {CHANNEL} — is it still an admin?"
    return "ok", f"@{name} is alive — {CHANNEL} has {count['result']} subscribers"


CHECKS = [
    ("The bot's files", check_files_present),
    ("The code", check_code_loads),
    ("Building a digest", check_digest_renders),
    ("Surviving a cut-off AI reply", check_cut_off_reply_is_survivable),
    ("The news sources", check_news_source_answers),
    ("The channel", check_channel_was_fed),
    ("Telegram", check_telegram),
]

MARK = {"ok": "ok  ", "fail": "FAIL", "skip": "skip"}


def main():
    print("\nReality Sci-Fi Check — smoke test\n")
    tally = {"ok": 0, "fail": 0, "skip": 0}
    for label, check in CHECKS:
        try:
            state, message = check()
        except Exception as err:               # a check must never crash the run
            state, message = "fail", f"The check itself broke — {type(err).__name__}: {err}"
        tally[state] += 1
        print(f" {MARK[state]}  {label}: {message}")

    print()
    if tally["fail"]:
        print(f"BROKEN — {tally['fail']} failed, {tally['ok']} passed, "
              f"{tally['skip']} skipped\n")
        return 1
    print(f"WORKING — {tally['ok']} passed, {tally['skip']} skipped\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
