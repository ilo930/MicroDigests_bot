"""
reply_core.py — the "talk to it" logic for MicroDigests_bot.

Platform-agnostic: given the text of a Telegram message, it returns a list of
reply strings (HTML). The Vercel webhook (api/telegram.py) is a thin adapter over
this, and it's fully testable offline. It reuses news_bot.py so replies sound
exactly like the digest.

Commands:
  more <topic>   -> a few MORE fresh items in a bucket (space/minerals/tech/society)
  deeper <n>     -> expand digest item #n with more detail + what to research next
  help           -> usage
"""

import os
import re
import json
import requests

import news_bot as nb
import players

# Where to read the last digest from (public raw file by default; a local path
# works too for offline testing).
LATEST_DIGEST_URL = os.environ.get(
    "LATEST_DIGEST_URL",
    "https://raw.githubusercontent.com/ilo930/MicroDigests_bot/main/state/latest_digest.json")

THEME_ALIASES = {
    "space": "space", "rocket": "space", "rockets": "space", "launch": "space",
    "launches": "space", "nasa": "space", "orbit": "space",
    "mineral": "minerals", "minerals": "minerals", "material": "minerals",
    "materials": "minerals", "mining": "minerals", "geology": "minerals",
    "rare": "minerals", "lithium": "minerals", "copper": "minerals",
    "tech": "tech", "frontier": "tech", "quantum": "tech", "defense": "tech",
    "defence": "tech", "ai": "tech", "chip": "tech", "chips": "tech",
    "bio": "tech", "biotech": "tech", "medicine": "tech", "compute": "tech",
    "society": "society", "power": "society", "geopolitics": "society",
    "policy": "society", "politics": "society",
    "earth": "earth", "planet": "earth", "nature": "earth", "climate": "earth",
    "ecosystem": "earth", "ecosystems": "earth", "wildlife": "earth",
    "biodiversity": "earth", "animals": "earth", "water": "earth",
    "ocean": "earth", "oceans": "earth", "weather": "earth",
    "cleanenergy": "earth", "renewable": "earth", "renewables": "earth",
    "solar": "earth", "wind": "earth", "clean": "earth", "energy": "earth",
    "grid": "earth", "coral": "earth", "reef": "earth", "marine": "earth",
    "meteorology": "earth", "forecast": "earth", "conservation": "earth",
}

HELP = (
    "🛰️ <b>Reality Sci-Fi Check — menu</b>\n"
    "<i>Reply with any of these. The number is a story's number in the digest.</i>\n\n"
    "🔎 <b>deeper 6</b> — go deep on post #6 (how it works + what to watch)\n"
    "👥 <b>players 6</b> — who's who behind post #6 (companies · countries)\n"
    "➕ <b>more space</b> — a few more fresh stories in a section\n"
    "      sections: <code>space</code> · <code>minerals</code> · <code>tech</code> · "
    "<code>earth</code> · <code>society</code>\n"
    "❓ <b>menu</b> — show this again\n\n"
    "<i>Tip: you can also just send a number (e.g.</i> <code>6</code><i>) to go deeper on it.</i>"
)


# ----------------------------------------------------------------------------

def load_latest():
    try:
        if LATEST_DIGEST_URL.startswith("http"):
            return requests.get(LATEST_DIGEST_URL, timeout=15).json()
        with open(LATEST_DIGEST_URL) as f:
            return json.load(f)
    except Exception as e:
        print(f"[reply] load_latest failed: {e}")
        return {"items": []}


def resolve_theme(phrase):
    for word in re.findall(r"[a-z]+", phrase.lower()):
        if word in THEME_ALIASES:
            return THEME_ALIASES[word]
    return None


def handle_text(text):
    """Return a list of HTML reply strings for an incoming message."""
    low = (text or "").strip().lower()
    if low in ("", "/start", "start", "help", "/help", "hi", "hello",
               "menu", "/menu", "options", "/options"):
        return [HELP]

    # A bare number ("6") is a shortcut for "deeper 6".
    if low.isdigit():
        return deeper(int(low))

    m = re.match(r"(?:/)?(?:deeper|deep|more on|expand)\s+#?(\d+)", low)
    if m:
        return deeper(int(m.group(1)))

    # players <n> -> who's who behind the field of digest post #n.
    m = re.match(r"(?:/)?(?:players|who|companies|landscape)\s+#?(\d+)\b", low)
    if m:
        return players_for_post(int(m.group(1)))

    m = re.match(r"(?:/)?(?:players|who|companies|landscape)\s+(.+)", low)
    if m:
        theme = resolve_theme(m.group(1))
        if not theme:
            return [f"Which field? Try <code>players space</code> / "
                    f"<code>tech</code> / <code>minerals</code> / "
                    f"<code>society</code> — or a post number like "
                    f"<code>players 6</code>.\n\n{HELP}"]
        out = players.render(theme)
        return [out] if out else ["No player map for that field yet."]

    m = re.match(r"(?:/)?(?:more|more of|show|give me)\s+(.+)", low)
    if m:
        theme = resolve_theme(m.group(1))
        if not theme:
            return [f"Which bucket? Try <code>more space</code> / "
                    f"<code>minerals</code> / <code>tech</code> / "
                    f"<code>society</code>.\n\n{HELP}"]
        return more_items(theme)

    # Bare topic word ("tech", "quantum", …) -> more of that bucket.
    theme = resolve_theme(low)
    if theme:
        return more_items(theme)
    return [f"Didn't catch that.\n\n{HELP}"]


def players_for_post(num):
    """Show the who's-who for the FIELD of digest post #num."""
    items = load_latest().get("items", [])
    by_n = {it.get("n"): it for it in items if it.get("n")}
    it = by_n.get(num) or (items[num - 1] if 1 <= num <= len(items) else None)
    if not it:
        return [f"Post #{num} isn't in the last digest (it had {len(items)} items).\n\n{HELP}"]
    theme = it.get("theme")
    out = players.render(theme) if theme else None
    if not out:
        meta = nb.THEMES.get(theme, {})
        label = meta.get("title", theme or "that field")
        return [f"No player map for <b>{nb.esc(label)}</b> yet — try "
                f"<code>players space</code> / <code>tech</code> / "
                f"<code>minerals</code>."]
    intro = (f"👥 <b>Players behind post #{num}</b> "
             f"<i>({nb.esc(nb.THEMES.get(theme, {}).get('title', theme))})</i>\n\n")
    return [intro + out]


def more_items(theme, n=3):
    meta = nb.THEMES[theme]
    seen_links = {it.get("link") for it in load_latest().get("items", [])}
    cands = [c for c in nb.fetch_candidates(only_theme=theme)
             if c["link"] and c["link"] not in seen_links]
    if not cands:
        return [f"No fresh {meta['title']} items right now — try again later."]

    picked = cands[:n]
    nb.analyze_items({theme: picked})  # one Groq call, fills the voice fields
    header = f"{meta['emoji']} <b>MORE — {meta['title']}</b>"
    blocks = [nb.format_item(it, {}) for it in picked]  # no live prices in replies
    return [header + "\n\n" + "\n\n".join(blocks)]


DEEPER_SYSTEM = """You help a curious reader (new to the domain) go DEEPER on ONE story, staying grounded in the article text provided. Use only facts in the text; if you add widely-known background, keep it accurate and general — never invent specifics.

Return ONLY JSON:
{"gist": "...", "how": "...", "why": "...", "watch": ["...", "...", "..."]}
- gist: what happened, vivid but factual (1-2 sentences).
- how: the mechanism / technology explained simply, unpacking jargon (1-2 sentences).
- why: the real-world / balance-of-power implications (1-2 sentences).
- watch: 2-3 concrete, specific things to follow or research next."""


def deeper(num):
    items = load_latest().get("items", [])
    by_n = {it.get("n"): it for it in items if it.get("n")}
    it = by_n.get(num) or (items[num - 1] if 1 <= num <= len(items) else None)
    if not it:
        return [f"Item #{num} isn't in the last digest (it had {len(items)} items).\n\n{HELP}"]

    grounding = it.get("text") or it.get("why") or it.get("headline") or ""
    user = f"HEADLINE: {it.get('headline')}\nARTICLE TEXT: {grounding[:1800]}"
    raw = nb.groq_chat(DEEPER_SYSTEM, user, temperature=0.35, max_tokens=1200,
                       label=":deeper")
    d = nb.extract_json(raw)
    if not d:
        return [f"Couldn't expand that one right now — try again in a moment."]

    lines = [f"🔎 <b>Deeper — {nb.esc(it.get('headline'))}</b>", ""]
    if d.get("gist"):
        lines.append(f"› <b>The gist:</b> {nb.esc(d['gist'])}")
    if d.get("how"):
        lines.append(f"› <b>How it works:</b> {nb.esc(d['how'])}")
    if d.get("why"):
        lines.append(f"› <b>Why it matters:</b> {nb.esc(d['why'])}")
    watch = d.get("watch") or []
    if watch:
        lines.append("› <b>Watch next:</b>")
        lines += [f"   • {nb.esc(w)}" for w in watch[:3]]
    if it.get("link"):
        href = __import__("html").escape(it["link"], quote=True)
        lines.append(f"\n› <a href=\"{href}\">{nb.esc(it.get('source'))} ↗</a>")
    return ["\n".join(lines)]
