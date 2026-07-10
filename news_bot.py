"""
MicroDigests_bot — "Reality Sci-Fi Check"

A Telegram digest that keeps you ahead of the curve on space, critical minerals,
the space economy, and how they reshape society — narrated with the "we live in
the future now" wonder, explained like you're new to it, and grounded in the
actual article text (never invented from a headline).

Pipeline:
  1. fetch      — parse full-text RSS feeds (with fallbacks), collect recent items
  2. dedup      — drop anything already sent (state/seen.json)
  3. select     — LLM pass 1 ranks + tags items to the 4 themes, keeps the best few
  4. analyze    — LLM pass 2 writes each item in-voice (sci-fi hook + ELI5 +
                  why-it-matters + market), citing ONLY watchlist tickers
  5. prices     — attach REAL prices/ranges (yfinance) to cited tickers, in code
  6. format     — one Telegram message per theme (HTML), under the 4096 limit
  7. send       — deliver (or print, if DRY_RUN)
  8. persist    — update seen.json + write latest_digest.json (for the reply bot)

Env:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY  — required to send/analyze
  DRY_RUN=1   — print messages to stdout instead of sending to Telegram
  MOCK_LLM=1  — skip Groq; fabricate structured output from real fetched items
  DEBUG=1     — print raw LLM response heads for troubleshooting
"""

import os
import re
import json
import html
import time
import hashlib
import datetime
from urllib.parse import urlparse

import feedparser
import requests

from watchlist import all_tickers, render_for_prompt

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

DRY_RUN = os.environ.get("DRY_RUN", "") == "1"
MOCK_LLM = os.environ.get("MOCK_LLM", "") == "1"
DEBUG = os.environ.get("DEBUG", "") == "1"

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
SEEN_PATH = os.path.join(STATE_DIR, "seen.json")
LATEST_PATH = os.path.join(STATE_DIR, "latest_digest.json")

# How far back to look (cadence is every 3 days; small overlap avoids gaps).
LOOKBACK_DAYS = 4
PER_FEED_LIMIT = 10        # candidates pulled per feed
MAX_CANDIDATES = 22        # freshest N sent to the ranking LLM (free-tier TPM budget)
PER_THEME_KEEP = 2         # items kept per theme after ranking
SELECT_CHARS = 120         # summary chars per candidate in the ranking prompt
ANALYZE_CHARS = 1400       # article chars per item in the analysis prompt
TELEGRAM_LIMIT = 4096

# Groq free tier is ~8000 tokens/minute, so keep output reservations tight.
SELECT_MAX_TOKENS = 800
ANALYZE_MAX_TOKENS = 2000

# Browser-ish headers — many news sites 403 the default feedparser UA.
FEED_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Each feed lists its theme and a URL fallback chain: we use the first URL that
# returns entries. mining.com is full-text but 403s from datacenter IPs (GitHub),
# so it falls back to another full-text feed, then to a Google News RSS query.
_GN_MINERALS = ("https://news.google.com/rss/search?q=%22critical+minerals%22+OR+"
                "%22rare+earth%22+OR+lithium+mining+OR+copper+mine+when:7d"
                "&hl=en-US&gl=US&ceid=US:en")
FEEDS = [
    {"theme": "space",     "urls": ["https://spaceflightnow.com/feed/"]},
    {"theme": "space",     "urls": ["https://arstechnica.com/space/feed/"]},
    {"theme": "space",     "urls": ["https://spacenews.com/feed/"]},
    {"theme": "resources", "urls": ["https://payloadspace.com/feed/"]},
    {"theme": "minerals",  "urls": ["https://www.mining.com/feed/",
                                    "https://im-mining.com/feed/",
                                    _GN_MINERALS]},
]

# Theme presentation. Order = message order.
THEMES = {
    "space": {
        "emoji": "🚀",
        "title": "SPACE",
        "tagline": "Missions, launches, and what's actually flying up there.",
    },
    "minerals": {
        "emoji": "⛏️",
        "title": "MINERALS & GEOLOGY",
        "tagline": "The resource layer underneath the future economy.",
    },
    "resources": {
        "emoji": "🛰️",
        "title": "SPACE ECONOMY & RESOURCES",
        "tagline": "Off-world business, mining, and the new frontier's balance sheet.",
    },
    "society": {
        "emoji": "🌍",
        "title": "SOCIETY & GEOPOLITICS",
        "tagline": "How the frontier quietly reshapes power on the ground.",
    },
}

NOISE_KEYWORDS = ["podcast", "sponsored", "webinar", "advertisement"]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def item_id(link, title):
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]


def strip_html(raw, limit=3000):
    """Turn feed HTML into clean plain text for grounding."""
    if not raw:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def domain_of(url):
    try:
        return urlparse(url).netloc.replace("www.", "") or "source"
    except Exception:
        return "source"


def extract_json(text):
    """Robustly pull a JSON object out of a model response."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {}


# ----------------------------------------------------------------------------
# 1. Fetch
# ----------------------------------------------------------------------------

def _parse_feed(url):
    """Fetch bytes with a browser UA and parse; return feedparser result or None."""
    try:
        resp = requests.get(url, headers=FEED_HEADERS, timeout=30)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        print(f"[fetch] error {url}: {e}")
        return None


def fetch_candidates():
    cutoff = _now() - datetime.timedelta(days=LOOKBACK_DAYS)
    out = []
    for feed in FEEDS:
        default_theme = feed["theme"]
        parsed = None
        used_url = None
        for url in feed["urls"]:
            parsed = _parse_feed(url)
            if parsed and parsed.entries:
                used_url = url
                break
            print(f"[fetch] no entries from {url}, trying fallback…")
        if not parsed or not parsed.entries:
            print(f"[fetch] all sources failed for theme={default_theme}")
            continue

        for entry in parsed.entries[:PER_FEED_LIMIT]:
            title = (entry.get("title") or "").strip()
            if not title or any(k in title.lower() for k in NOISE_KEYWORDS):
                continue

            published_dt = None
            for key in ("published_parsed", "updated_parsed"):
                if entry.get(key):
                    published_dt = datetime.datetime(*entry[key][:6],
                                                     tzinfo=datetime.timezone.utc)
                    break
            if published_dt and published_dt < cutoff:
                continue

            body = ""
            if entry.get("content"):
                body = entry["content"][0].get("value", "")
            body = body or entry.get("summary", "") or entry.get("description", "")

            link = entry.get("link", "")
            # Google News items carry the real publisher under entry.source.
            src = domain_of(link) if link else domain_of(used_url)
            if entry.get("source") and entry["source"].get("title"):
                src = entry["source"]["title"]

            out.append({
                "id": item_id(link, title),
                "title": title,
                "link": link,
                "source": src,
                "published": published_dt.isoformat() if published_dt else "",
                "published_dt": published_dt or _now(),
                "text": strip_html(body),
                "default_theme": default_theme,
            })

    # Freshest first, so the per-minute LLM budget spends on recent news.
    out.sort(key=lambda c: c["published_dt"], reverse=True)
    print(f"[fetch] {len(out)} candidates from {len(FEEDS)} feeds")
    return out


# ----------------------------------------------------------------------------
# 2. Dedup
# ----------------------------------------------------------------------------

def load_seen():
    try:
        with open(SEEN_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen(seen):
    cutoff = (_now() - datetime.timedelta(days=30)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SEEN_PATH, "w") as f:
        json.dump(seen, f, indent=2)


def drop_seen(candidates, seen):
    fresh = [c for c in candidates if c["id"] not in seen]
    print(f"[dedup] {len(fresh)} fresh ({len(candidates) - len(fresh)} already sent)")
    return fresh


# ----------------------------------------------------------------------------
# Groq (rate-limit aware; free tier is ~8000 tokens/minute)
# ----------------------------------------------------------------------------

def groq_chat(system_prompt, user_prompt, temperature=0.3, max_tokens=2000, label=""):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}
    data = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # gpt-oss reasoning models: keep the reasoning trace short to fit the TPM budget.
    if GROQ_MODEL.startswith("openai/gpt-oss"):
        data["reasoning_effort"] = "low"

    for attempt in range(5):
        try:
            r = requests.post(GROQ_URL, json=data, headers=headers, timeout=120)
            j = r.json()
            if "error" in j:
                err = j["error"]
                msg = err.get("message", "")
                if err.get("code") == "rate_limit_exceeded" or err.get("type") == "tokens":
                    m = re.search(r"try again in ([0-9.]+)s", msg)
                    wait = min((float(m.group(1)) + 1.5) if m else 20.0, 65.0)
                    print(f"[groq{label}] rate limited; waiting {wait:.0f}s "
                          f"(attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                print(f"[groq{label}] API error: {err}")
                return ""
            content = j["choices"][0]["message"]["content"]
            if DEBUG:
                print(f"[groq{label}] raw head: {content[:200]!r}")
            return content
        except Exception as e:
            print(f"[groq{label}] attempt {attempt + 1} failed: {e}")
            time.sleep(3 * (attempt + 1))
    return ""


# ----------------------------------------------------------------------------
# 3. Select (LLM pass 1: rank + tag to themes)
# ----------------------------------------------------------------------------

SELECT_SYSTEM = """You curate a personal briefing for someone who wants to feel the "we live in the future" wonder of space, critical minerals, the space economy, and how they reshape society. They are still LEARNING this domain, so favour items that are genuinely novel, surprising, or consequential over routine/incremental updates.

You will get a numbered list of candidate news items. Assign each a theme and a relevance score.

Themes:
- space     = missions, launches, spacecraft, astronomy discoveries
- minerals  = critical minerals, mining, rare earths, geology, resource supply
- resources = space economy / off-world industry / ISRU / space mining / space business
- society   = geopolitics, policy, economics, how space & minerals reshape power and daily life

Score 0-10: 10 = jaw-dropping / high-impact / novel; 0 = routine, dull, or off-topic.
Drop press-release fluff, minor personnel news, and pure stock-promotion.

Return ONLY compact JSON, no prose:
{"items":[{"i":<number>,"theme":"space|minerals|resources|society","score":<0-10>}]}"""


def select_items(candidates):
    if not candidates:
        return {}
    candidates = candidates[:MAX_CANDIDATES]

    if MOCK_LLM:
        for c in candidates:
            c["_theme"] = c["default_theme"]
        ranked = candidates
    else:
        lines = [f"[{i}] ({c['default_theme']}) {c['title']} — {c['text'][:SELECT_CHARS]}"
                 for i, c in enumerate(candidates)]
        raw = groq_chat(SELECT_SYSTEM, "Candidates:\n" + "\n".join(lines),
                        temperature=0.2, max_tokens=SELECT_MAX_TOKENS, label=":select")
        parsed = extract_json(raw).get("items", [])
        if not parsed and raw:
            print(f"[select] unparseable ranking head: {raw[:200]!r}")
        score_by_idx = {}
        for it in parsed:
            try:
                i = int(it["i"])
            except Exception:
                continue
            if 0 <= i < len(candidates):
                candidates[i]["_theme"] = it.get("theme") or candidates[i]["default_theme"]
                score_by_idx[i] = float(it.get("score", 0))
        if not score_by_idx:
            print("[select] no usable ranking; falling back to recency")
            for i, c in enumerate(candidates):
                c["_theme"] = c["default_theme"]
                score_by_idx[i] = 5.0
        ranked = [candidates[i] for i in sorted(score_by_idx, key=score_by_idx.get,
                                                reverse=True)]

    by_theme = {t: [] for t in THEMES}
    for c in ranked:
        theme = c.get("_theme", c["default_theme"])
        if theme not in by_theme:
            theme = c["default_theme"]
        if len(by_theme[theme]) < PER_THEME_KEEP:
            by_theme[theme].append(c)
    total = sum(len(v) for v in by_theme.values())
    n_themes = sum(1 for v in by_theme.values() if v)
    print(f"[select] kept {total} items across {n_themes} themes")
    return {t: v for t, v in by_theme.items() if v}


# ----------------------------------------------------------------------------
# 4. Analyze (LLM pass 2: write each item in-voice)
# ----------------------------------------------------------------------------

ANALYZE_SYSTEM = """You are the narrator of a "Reality Sci-Fi Check" — a personal briefing that makes the reader FEEL like they live in the future, while staying 100% factual. The reader is new to this domain, so explain plainly.

For EACH news item you receive (with its full article text), write these fields. Use ONLY facts present in the provided text — never invent details, numbers, or precedents.

- "headline": a short, vivid, accurate title (max ~90 chars).
- "scifi_hook": ONE sentence capturing the wonder / novelty — cinematic but strictly real. This is the "whoa, we live in the future" line and also conveys what happened. (e.g. "A company is manufacturing medicine in orbit and parachuting it back to the desert.")
- "eli5": ONE sentence explaining it like the reader is smart but brand-new to space/mining — unpack any jargon (ISRU, polymetallic nodule, rare-earth, etc.).
- "why": ONE sentence on why it matters for society / the real world / the balance of power.
- "tickers": array of ticker symbols from the WATCHLIST that could plausibly be affected. Use ONLY symbols from the watchlist. If the actual company is private or nothing fits, use [].
- "proxy_note": short string. If the key company is private/unlisted, say so and optionally name the nearest listed read-through FROM THE WATCHLIST (e.g. "Varda is private — nearest read-through RKLB"). Else "".
- "bias": "up" | "down" | "mixed" | "n/a" — likely directional read-through for the tickers (speculative).
- "rationale": ONE short sentence on the market read-through (speculative). No price targets.
- "confidence": "low" | "medium" | "high" — your confidence in the market read-through.

Rules:
- Every sentence must be defensible from the article text.
- Keep each field to ONE sentence. No markdown, no bullet characters inside fields.
- The market read-through is speculative and must never be phrased as advice.

Return ONLY JSON: {"items":[{...one object per input item, SAME order...}]}"""


def analyze_items(selected):
    """selected: {theme: [candidate,...]}. Returns same structure with analysis merged."""
    flat = []
    for theme, items in selected.items():
        for c in items:
            c["_theme"] = theme
            flat.append(c)
    if not flat:
        return selected

    if MOCK_LLM:
        for c in flat:
            _mock_analyze(c)
        return selected

    allowed = all_tickers()
    blocks = [f"### ITEM {i} (theme: {c['_theme']}, source: {c['source']})\n"
              f"TITLE: {c['title']}\nARTICLE TEXT: {c['text'][:ANALYZE_CHARS]}"
              for i, c in enumerate(flat)]
    user = ("WATCHLIST (only cite tickers from here):\n" + render_for_prompt() +
            "\n\n" + "\n\n".join(blocks))
    raw = groq_chat(ANALYZE_SYSTEM, user, temperature=0.35,
                    max_tokens=ANALYZE_MAX_TOKENS, label=":analyze")
    results = extract_json(raw).get("items", [])
    if not results and raw:
        print(f"[analyze] unparseable head: {raw[:200]!r}")

    for idx, c in enumerate(flat):
        a = results[idx] if idx < len(results) else {}
        c["headline"] = a.get("headline") or c["title"]
        c["scifi_hook"] = a.get("scifi_hook", "")
        c["eli5"] = a.get("eli5", "")
        c["why"] = a.get("why", "")
        c["proxy_note"] = a.get("proxy_note", "")
        c["bias"] = a.get("bias", "n/a")
        c["rationale"] = a.get("rationale", "")
        c["confidence"] = a.get("confidence", "low")
        c["tickers"] = [t for t in a.get("tickers", []) if t in allowed][:3]
    return selected


def _mock_analyze(c):
    c["headline"] = c["title"][:90]
    c["scifi_hook"] = "The sci-fi part: this is real and happening right now (mock)."
    c["eli5"] = "In plain terms: a simple explanation for a newcomer (mock)."
    c["why"] = "Why it matters: it nudges the real world in a concrete way (mock)."
    c["proxy_note"] = ""
    c["tickers"] = ["RKLB"] if c["_theme"] in ("space", "resources") else ["MP"]
    c["bias"] = "up"
    c["rationale"] = "Read-through is mildly positive (mock, speculative)."
    c["confidence"] = "low"


# ----------------------------------------------------------------------------
# 5. Prices (yfinance — real numbers, attached in code, never model-invented)
# ----------------------------------------------------------------------------

def fetch_prices(tickers):
    prices = {}
    if not tickers:
        return prices
    try:
        import yfinance as yf
    except Exception as e:
        print(f"[prices] yfinance unavailable: {e}")
        return prices
    for t in sorted(set(tickers)):
        try:
            hist = yf.Ticker(t).history(period="1mo")
            if hist is None or hist.empty:
                continue
            closes = hist["Close"].dropna()
            if closes.empty:
                continue
            prices[t] = {"last": round(float(closes.iloc[-1]), 2),
                         "low": round(float(closes.min()), 2),
                         "high": round(float(closes.max()), 2)}
        except Exception as e:
            print(f"[prices] {t} failed: {e}")
    print(f"[prices] resolved {len(prices)}/{len(set(tickers))} tickers")
    return prices


# ----------------------------------------------------------------------------
# 6. Format (one HTML message per theme)
# ----------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s or ""), quote=False)


def fmt_market_line(item, prices):
    tickers = item.get("tickers", [])
    parts = []
    for t in tickers:
        p = prices.get(t)
        if p:
            parts.append(f"<code>{esc(t)}</code> ${p['last']} (1mo {p['low']}–{p['high']})")
        else:
            parts.append(f"<code>{esc(t)}</code>")
    if parts:
        body = ", ".join(parts)
    elif item.get("proxy_note"):
        body = esc(item["proxy_note"])
    else:
        body = "No clean public proxy"

    tail = ""
    if item.get("rationale"):
        arrow = {"up": "↗", "down": "↘", "mixed": "↔"}.get(item.get("bias", "n/a"), "")
        tail = f" — {arrow} {esc(item['rationale'])}"
    conf = item.get("confidence", "low")
    return (f"📈 <b>Market</b> <i>(speculative, {esc(conf)} conf):</i> "
            f"{body}{tail} <i>Not advice.</i>")


def format_item(item, prices):
    lines = [f"▸ <b>{esc(item.get('headline'))}</b>"]
    if item.get("scifi_hook"):
        lines.append(f"✨ <b>The sci-fi part:</b> {esc(item['scifi_hook'])}")
    if item.get("eli5"):
        lines.append(f"🧒 <b>In plain terms:</b> {esc(item['eli5'])}")
    if item.get("why"):
        lines.append(f"🌍 <b>Why it matters:</b> {esc(item['why'])}")
    lines.append(fmt_market_line(item, prices))
    if item.get("link"):
        href = html.escape(item["link"], quote=True)
        lines.append(f"🔗 <a href=\"{href}\">{esc(item['source'])} ↗</a>")
    return "\n".join(lines)


def build_theme_messages(analyzed, prices, date_str):
    """Return a list of (theme, message_text) chunks, each under the TG limit."""
    messages = []
    for theme, meta in THEMES.items():
        items = analyzed.get(theme)
        if not items:
            continue
        header = (f"{meta['emoji']} <b>{meta['title']}</b> · <i>{date_str}</i>\n"
                  f"<i>{esc(meta['tagline'])}</i>")
        current = header
        for it in items:
            block = format_item(it, prices)
            candidate = current + "\n\n" + block
            if len(candidate) > TELEGRAM_LIMIT:
                messages.append((theme, current))
                current = (f"{meta['emoji']} <b>{meta['title']}</b> "
                           f"<i>(cont.)</i>\n\n" + block)
            else:
                current = candidate
        messages.append((theme, current))
    return messages


# ----------------------------------------------------------------------------
# 7. Send
# ----------------------------------------------------------------------------

def send_telegram(text):
    if DRY_RUN:
        print("\n" + "=" * 64)
        print(text)
        print("=" * 64)
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"[telegram] error {r.status_code}: {r.text}")
            return False
        return True
    except Exception as e:
        print(f"[telegram] failed: {e}")
        return False


# ----------------------------------------------------------------------------
# 8. Persist
# ----------------------------------------------------------------------------

def persist(analyzed, prices, date_str, seen):
    now_iso = _now().isoformat()
    flat = []
    for theme, items in analyzed.items():
        for c in items:
            seen[c["id"]] = now_iso
            flat.append({
                "theme": theme, "headline": c.get("headline"), "title": c["title"],
                "scifi_hook": c.get("scifi_hook"), "eli5": c.get("eli5"),
                "why": c.get("why"), "tickers": c.get("tickers"),
                "proxy_note": c.get("proxy_note"), "bias": c.get("bias"),
                "rationale": c.get("rationale"), "confidence": c.get("confidence"),
                "link": c["link"], "source": c["source"],
            })
    save_seen(seen)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LATEST_PATH, "w") as f:
        json.dump({"date": date_str, "generated_at": now_iso,
                   "prices": prices, "items": flat}, f, indent=2)
    print(f"[persist] wrote {len(flat)} items to state/")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    date_str = _now().strftime("%Y-%m-%d")
    print(f"[run] Reality Sci-Fi Check {date_str} "
          f"(dry_run={DRY_RUN}, mock_llm={MOCK_LLM}, model={GROQ_MODEL})")

    candidates = fetch_candidates()
    seen = load_seen()
    fresh = drop_seen(candidates, seen)
    if not fresh:
        print("[run] nothing fresh to send")
        return

    selected = select_items(fresh)
    if not selected:
        print("[run] nothing selected")
        return

    analyzed = analyze_items(selected)

    all_t = [t for items in analyzed.values() for c in items for t in c.get("tickers", [])]
    prices = fetch_prices(all_t)

    messages = build_theme_messages(analyzed, prices, date_str)
    lead = (f"🛰️ <b>REALITY SCI-FI CHECK</b> — <i>{date_str}</i>\n"
            f"<i>Your window into the future that's already here — "
            f"{len(messages)} dispatches incoming.</i>")
    ok = send_telegram(lead)
    for _theme, msg in messages:
        ok = send_telegram(msg) and ok
        if not DRY_RUN:
            time.sleep(1)  # be gentle with Telegram rate limits

    # Only record state on a real send (not dry-run tests, not mock data).
    if ok and not MOCK_LLM and not DRY_RUN:
        persist(analyzed, prices, date_str, seen)
    print("[run] done")


if __name__ == "__main__":
    main()
