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
}

HELP = (
    "🛰️ <b>Reality Sci-Fi Check</b> — talk to me:\n\n"
    "› <b>more &lt;topic&gt;</b> — more fresh items in a bucket\n"
    "   <code>more tech</code> · <code>more space</code> · "
    "<code>more minerals</code> · <code>more society</code>\n"
    "› <b>deeper &lt;n&gt;</b> — go deep on item #n from the last digest\n"
    "   <code>deeper 3</code>\n"
    "› <b>players &lt;topic&gt;</b> — who's who in a field (company · country)\n"
    "   <code>players space</code> · <code>players tech</code> · "
    "<code>players minerals</code>\n"
    "› <b>help</b> — this message"
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
    if low in ("", "/start", "start", "help", "/help", "hi", "hello"):
        return [HELP]

    m = re.match(r"(?:/)?(?:deeper|deep|more on|expand)\s+#?(\d+)", low)
    if m:
        return deeper(int(m.group(1)))

    m = re.match(r"(?:/)?(?:players|who|companies|landscape)\s+(.+)", low)
    if m:
        theme = resolve_theme(m.group(1))
        if not theme:
            return [f"Which field? Try <code>players space</code> / "
                    f"<code>tech</code> / <code>minerals</code> / "
                    f"<code>society</code>.\n\n{HELP}"]
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
