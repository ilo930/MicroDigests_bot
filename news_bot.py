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
# Optional extra broadcast targets (e.g. a channel/group to share with friends),
# comma-separated. Your private DM (TELEGRAM_CHAT_ID) always still gets the digest.
EXTRA_CHATS = [c.strip() for c in
               os.environ.get("TELEGRAM_EXTRA_CHATS", "").split(",") if c.strip()]
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
CANDIDATES_PER_THEME = 8   # freshest N per theme in the ranking pool (fair share)
MAX_CANDIDATES = 30        # overall cap on the ranking pool (free-tier TPM budget)
MAX_ITEMS_TOTAL = 7        # stories written up per digest (the "glimpse" budget)
PER_THEME_MAX = 3          # cap any one bucket so it can't dominate the digest
CORE_THEMES = ("space", "minerals", "tech", "earth")  # each guaranteed >=1 if available
SELECT_CHARS = 120         # summary chars per candidate in the ranking prompt
ANALYZE_CHARS = 1300       # article chars per item in the analysis prompt
TELEGRAM_LIMIT = 4096

# Groq free tier is ~8000 tokens/minute; gpt-oss spends completion tokens on
# reasoning too, so the ranking needs headroom or its JSON gets truncated.
SELECT_MAX_TOKENS = 2200
ANALYZE_MAX_TOKENS = 2000

# Browser-ish headers — many news sites 403 the default feedparser UA.
FEED_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Each feed lists its theme and a URL fallback chain: we use the first URL that
# returns entries. mining.com is full-text but 403s from datacenter IPs (GitHub),
# so it falls back to another full-text feed, then to a Google News RSS query.
_GN = "https://news.google.com/rss/search?q={q}+when:7d&hl=en-US&gl=US&ceid=US:en"
_GN_MINERALS = _GN.format(q="%22critical+minerals%22+OR+%22rare+earth%22+OR+lithium+mining+OR+copper+mine")
_GN_QUANTUM = _GN.format(q="%22quantum+computing%22")
_GN_DEFENSE = _GN.format(q="(military+OR+defense)+technology+(hypersonic+OR+drone+OR+chip+OR+AI)")
_GN_AIBIO = _GN.format(q="(AI+OR+%22machine+learning%22)+(drug+discovery+OR+bioprinting+OR+protein+OR+biotech)")
_GN_SOCIETY = _GN.format(q="(space+OR+defense+OR+%22rare+earth%22+OR+quantum)+(policy+OR+geopolitics+OR+sanctions+OR+treaty+OR+%22export+controls%22)")
_GN_NUCROBO = _GN.format(q="(space+OR+defense+OR+energy)+(%22nuclear+reactor%22+OR+SMR+OR+fusion+OR+robotics+OR+%22humanoid+robot%22)")
# LIVING EARTH — good news for the planet: clean energy, ecosystems, water, weather
# science, and (rarely) a major climate development.
_GN_CLEANENERGY = _GN.format(q="(solar+OR+wind+OR+geothermal+OR+%22grid+battery%22+OR+renewable)+energy+(record+OR+breakthrough+OR+milestone)")
_GN_ECOSYSTEMS = _GN.format(q="(wildlife+OR+biodiversity+OR+conservation+OR+rewilding+OR+%22coral+reef%22+OR+species)+(recovery+OR+comeback+OR+protected+OR+restored)")
_GN_WATER = _GN.format(q="(ocean+OR+%22freshwater%22+OR+river+OR+aquifer+OR+desalination+OR+%22water+supply%22)+(discovery+OR+cleanup+OR+restored+OR+breakthrough)")
_GN_WEATHER = _GN.format(q="(%22weather+forecasting%22+OR+meteorology+OR+%22weather+model%22+OR+%22weather+satellite%22)+(AI+OR+breakthrough+OR+advance+OR+launch)")
_GN_CLIMATE = _GN.format(q="climate+change+(record+OR+extreme+OR+tipping+point+OR+milestone)")

# NON-WESTERN DESKS — same reliable Google-News mechanism but non-US editions, so
# the digest carries more than one civilization's framing. India (a top space/tech/
# minerals nation) and Hong Kong (surfaces SCMP & broader Asia coverage), in English.
def _gnr(q, hl, gl):
    return (f"https://news.google.com/rss/search?q={q}+when:7d"
            f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}")
_GN_IN_SPACE = _gnr("space+OR+ISRO+OR+satellite+OR+launch", "en-IN", "IN")
_GN_IN_TECH = _gnr("(quantum+OR+semiconductor+OR+chip+OR+AI+OR+robot)", "en-IN", "IN")
_GN_IN_MIN = _gnr("(%22rare+earth%22+OR+lithium+OR+copper+OR+%22critical+minerals%22+OR+mining)", "en-IN", "IN")
_GN_AS_TECH = _gnr("(China+OR+Asia)+(quantum+OR+chip+OR+semiconductor+OR+AI+OR+space+OR+%22rare+earth%22)", "en-HK", "HK")

FEEDS = [
    # SPACE — missions, launches, discoveries, and the off-world economy.
    {"theme": "space",    "urls": ["https://spaceflightnow.com/feed/"]},
    {"theme": "space",    "urls": ["https://arstechnica.com/space/feed/"]},
    {"theme": "space",    "urls": ["https://spacenews.com/feed/"]},
    {"theme": "space",    "urls": ["https://payloadspace.com/feed/"]},
    {"theme": "space",    "urls": ["https://www.nasa.gov/feed/"]},                              # NASA (primary)
    {"theme": "space",    "urls": ["https://www.esa.int/rssfeed/Our_Activities/Space_Science"]},  # ESA (primary)
    {"theme": "space",    "urls": ["https://global.jaxa.jp/rss/press.rdf"]},                    # JAXA (primary)
    {"theme": "space",    "urls": [_GN_IN_SPACE]},   # India/Asia space desk
    # MINERALS & MATERIALS — mining.com is full-text but 403s from CI, so it falls
    # back to another full-text feed, then a Google News query.
    {"theme": "minerals", "urls": ["https://www.mining.com/feed/",
                                   "https://im-mining.com/feed/", _GN_MINERALS]},
    {"theme": "minerals", "urls": [_GN_IN_MIN]},     # India/Asia minerals desk
    # FRONTIER TECH — quantum, chips/AI, defense tech, AI-driven bio / space medicine.
    {"theme": "tech",     "urls": ["https://thequantuminsider.com/feed/", _GN_QUANTUM]},
    {"theme": "tech",     "urls": ["https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
                                   _GN_DEFENSE]},
    {"theme": "tech",     "urls": [_GN_AIBIO]},
    {"theme": "tech",     "urls": [_GN_NUCROBO]},
    {"theme": "tech",     "urls": [_GN_IN_TECH]},    # India tech desk
    {"theme": "tech",     "urls": [_GN_AS_TECH]},    # Hong Kong / Asia (SCMP etc.)
    {"theme": "tech",     "urls": ["https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms"]},  # India deep-tech
    {"theme": "tech",     "urls": ["https://quantumzeitgeist.com/feed/"]},   # independent quantum
    {"theme": "tech",     "urls": ["https://phys.org/rss-feed/"]},           # independent science (broad)
    # LIVING EARTH — the planet as a stakeholder: clean energy, ecosystems &
    # wildlife, water & oceans, weather science, and rare major climate flags.
    {"theme": "earth",    "urls": [_GN_CLEANENERGY]},
    {"theme": "earth",    "urls": [_GN_ECOSYSTEMS]},
    {"theme": "earth",    "urls": [_GN_WATER]},
    {"theme": "earth",    "urls": [_GN_WEATHER]},
    {"theme": "earth",    "urls": [_GN_CLIMATE]},
    {"theme": "earth",    "urls": ["https://www.ctvc.co/feed"]},   # Sightline Climate (indie climate-tech)
    # SOCIETY & POWER — geopolitics/policy of the frontier. Not a core theme, so it
    # only earns a digest slot when it scores high; also powers "more society".
    {"theme": "society",  "urls": [_GN_SOCIETY]},
    # STATE MEDIA — the DIRECT Chinese & Russian voice, deliberately included so you
    # hear it firsthand, but every item is clearly labelled in the digest as state
    # media ("pinch of salt"). Independent outlets still dominate the mix.
    {"theme": "society",  "urls": ["http://www.chinadaily.com.cn/rss/world_rss.xml"]},
    {"theme": "society",  "urls": ["https://www.cgtn.com/subscribe/rss/section/world.xml"]},
    {"theme": "society",  "urls": ["http://en.people.cn/rss/China.xml"]},
]

# Theme presentation. Order = message order.
THEMES = {
    "space": {
        "emoji": "🚀",
        "title": "Space",
        "tagline": "What's flying, landing, and being discovered up there.",
    },
    "minerals": {
        "emoji": "⛏️",
        "title": "Minerals & Mining",
        "tagline": "The raw materials the future is built from.",
    },
    "tech": {
        "emoji": "🔬",
        "title": "Frontier Tech",
        "tagline": "Quantum, chips, AI, robots, and medicine leaving the lab.",
    },
    "earth": {
        "emoji": "🌍",
        "title": "Living Earth",
        "tagline": "Good news for the planet — clean energy, wildlife, water, and the science of weather.",
    },
    "society": {
        "emoji": "🌍",
        "title": "Society & Power",
        "tagline": "How the frontier reshapes who holds the cards.",
    },
}

NOISE_KEYWORDS = ["podcast", "sponsored", "webinar", "advertisement"]

# Rotating "state of play" facts shown in the header to ground the reader. Curated
# (approximate, as of ~2025-26) rather than AI-guessed, so the numbers are real.
CONTEXT_FACTS = [
    "~11,000+ active satellites orbit Earth — over half are SpaceX Starlink.",
    "~90 nations operate a satellite, but only a handful can launch their own.",
    "Only 3 countries have launched humans to orbit on their own: Russia, the US, China.",
    "China refines ~90% of the world's rare earths — the bottleneck is processing, not the rocks.",
    "Taiwan's TSMC makes the majority of the world's most advanced chips.",
    "One ASML EUV machine (needed for cutting-edge chips) costs ~$150M+ — only ASML makes them.",
    "Today's quantum computers have ~100–1,000 qubits; useful ones need millions.",
    "The Moon's south pole is the new race — water ice there could become rocket fuel.",
    "The US, China and Russia account for most orbital launches each year.",
    "Tens of thousands more satellites are planned this decade — low orbit is filling up.",
    "Lithium, copper and rare earths are the 'oil' of the electric + AI era.",
    "Reusable rockets cut launch cost ~10x — the reason spaceflight suddenly scaled.",
    "In the Global Innovation Index, Switzerland, Sweden and the US lead — China is the fastest-rising major economy.",
    "On Harvard's Critical & Emerging Technologies Index, the US ranks #1 and China #2 — the tech era's two-horse race.",
]


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


def fetch_candidates(only_theme=None):
    cutoff = _now() - datetime.timedelta(days=LOOKBACK_DAYS)
    out = []
    for feed in FEEDS:
        default_theme = feed["theme"]
        if only_theme and default_theme != only_theme:
            continue
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
            src = domain_of(link) if link else domain_of(used_url)
            # Google News wraps the real publisher in entry.source; other feeds
            # sometimes put tracking junk there, so only trust it for Google News.
            if "news.google.com" in (used_url or "") and entry.get("source", {}).get("title"):
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

    # Drop near-duplicate stories that show up across feeds (same event twice).
    deduped, keys = [], []
    for c in out:
        k = _title_key(c["title"])
        if k and any(len(k & pk) / max(len(k | pk), 1) >= 0.6 for pk in keys):
            continue
        keys.append(k)
        deduped.append(c)
    if len(deduped) < len(out):
        print(f"[fetch] merged {len(out) - len(deduped)} near-duplicate stories")

    scope = f" ({only_theme})" if only_theme else f" from {len(FEEDS)} feeds"
    print(f"[fetch] {len(deduped)} candidates{scope}")
    return deduped


def _title_key(title):
    """Significant-word set for cheap near-duplicate detection."""
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3}


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
- space     = missions, launches, spacecraft, astronomy discoveries, the space economy, ISRU, in-space manufacturing
- minerals  = critical minerals, mining, rare earths, geology, materials, resource supply
- tech      = quantum computing, semiconductors/chips, AI, robotics & humanoids, nuclear & fusion energy tech, military & defense TECHNOLOGY (the tech itself), and AI-driven biotech / medicine made in space
- earth     = the living planet as a stakeholder: clean/renewable energy, ecosystems & wildlife & biodiversity, oceans & water, meteorology / weather science, and (rarely, only if MAJOR) a serious climate development. Strongly favour GOOD news for the planet and other species — not just human interests.
- society   = geopolitics, policy, economics — how space, minerals & tech reshape power and daily life

For "tech", the DEFENSE angle means the TECHNOLOGY/HARDWARE itself (weapons systems, drones, lasers, hypersonics, chips, AI, satellites, sensors) — NOT troop movements, espionage/spy arrests, budgets, contracts, or personnel. Score those low, or tag them "society" if geopolitically important.

Score 0-10: 10 = jaw-dropping / high-impact / novel; 0 = routine, dull, or off-topic.
Drop press-release fluff, minor personnel news, and pure stock-promotion.

PRIORITISE genuine SCIENCE and TECHNOLOGY substance — discoveries, breakthroughs, missions, launches, hard results — and INDEPENDENT / primary reporting (space agencies, research, specialist outlets). DOWN-rank pure politics, opinion, geopolitics-as-sport, and propaganda/spin unless the underlying development is itself genuinely consequential. Judge every item — state-media included — on its substance, not its framing.

Return ONLY compact JSON, no prose:
{"items":[{"i":<number>,"theme":"space|minerals|tech|earth|society","score":<0-10>}]}"""


def select_items(candidates):
    if not candidates:
        return {}

    # Build the ranking pool with a fair share per theme. Candidates are already
    # freshest-first; we cap each theme, then ROUND-ROBIN across themes so the
    # global MAX_CANDIDATES cut can never starve a slow feed (e.g. minerals via a
    # Google-News fallback with older items) just because faster feeds produced
    # newer stories. Every theme keeps representation up to the cap.
    per_theme = {}
    for c in candidates:
        per_theme.setdefault(c["default_theme"], []).append(c)
    for t in per_theme:
        per_theme[t] = per_theme[t][:CANDIDATES_PER_THEME]
    pool, depth = [], 0
    while len(pool) < MAX_CANDIDATES:
        added = False
        for lst in per_theme.values():
            if depth < len(lst):
                pool.append(lst[depth])
                added = True
                if len(pool) >= MAX_CANDIDATES:
                    break
        if not added:
            break
        depth += 1
    candidates = pool

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
            # Salvage complete objects from a truncated/partial JSON response.
            parsed = [{"i": int(m[0]), "theme": m[1], "score": float(m[2])}
                      for m in re.findall(
                          r'"i"\s*:\s*(\d+)\s*,\s*"theme"\s*:\s*"(\w+)"\s*,'
                          r'\s*"score"\s*:\s*([\d.]+)', raw)]
            print(f"[select] salvaged {len(parsed)} ranked items from partial JSON")
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

    def theme_of(c):
        t = c.get("_theme", c["default_theme"])
        return t if t in THEMES else c["default_theme"]

    # Pick a GLOBAL top-N (the "glimpse" budget) rather than a fixed quota per
    # theme: first guarantee each core theme its best item, then fill the rest by
    # overall rank, capping any single theme so it can't swamp the digest.
    chosen, chosen_ids, counts = [], set(), {t: 0 for t in THEMES}

    for t in CORE_THEMES:
        picked = False
        for c in ranked:
            if c["id"] not in chosen_ids and theme_of(c) == t:
                chosen.append(c); chosen_ids.add(c["id"]); counts[t] += 1
                picked = True; break
        if not picked:
            # The LLM may have re-tagged this bucket's items into other themes
            # (or scored them all low). If the bucket's OWN feed returned anything,
            # still surface its best, so a core theme is never silently starved.
            for c in ranked:
                if c["id"] not in chosen_ids and c["default_theme"] == t:
                    c["_theme"] = t
                    chosen.append(c); chosen_ids.add(c["id"]); counts[t] += 1
                    break
    for c in ranked:
        if len(chosen) >= MAX_ITEMS_TOTAL:
            break
        if c["id"] in chosen_ids or counts[theme_of(c)] >= PER_THEME_MAX:
            continue
        chosen.append(c); chosen_ids.add(c["id"]); counts[theme_of(c)] += 1

    # User rule: at most 2 state-media items per digest. Keep the 2 best-ranked,
    # drop the rest, and backfill freed slots with the next non-state candidates.
    rank_pos = {c["id"]: i for i, c in enumerate(ranked)}
    state_in = sorted((c for c in chosen if state_media_iso(c)),
                      key=lambda c: rank_pos.get(c["id"], 10 ** 6))
    if len(state_in) > 2:
        keep_ids = {c["id"] for c in state_in[:2]}
        chosen = [c for c in chosen
                  if not state_media_iso(c) or c["id"] in keep_ids]
        chosen_ids = {c["id"] for c in chosen}
        counts = {t: 0 for t in THEMES}
        for c in chosen:
            counts[theme_of(c)] += 1
        for c in ranked:
            if len(chosen) >= MAX_ITEMS_TOTAL:
                break
            if c["id"] in chosen_ids or state_media_iso(c):
                continue
            if counts[theme_of(c)] >= PER_THEME_MAX:
                continue
            chosen.append(c); chosen_ids.add(c["id"]); counts[theme_of(c)] += 1

    by_theme = {t: [] for t in THEMES}
    for c in chosen:
        by_theme[theme_of(c)].append(c)
    n_themes = sum(1 for v in by_theme.values() if v)
    print(f"[select] kept {len(chosen)} items across {n_themes} themes "
          f"({', '.join(f'{t}:{n}' for t, n in counts.items() if n)})")
    return {t: v for t, v in by_theme.items() if v}


# ----------------------------------------------------------------------------
# 4. Analyze (LLM pass 2: write each item in-voice)
# ----------------------------------------------------------------------------

ANALYZE_SYSTEM = """You are the narrator of a "Reality Sci-Fi Check" — a personal briefing that makes the reader FEEL like they live in the future, while staying 100% factual. The reader is new to this domain, so explain plainly.

For EACH news item you receive (labelled "### ITEM <n>", with its full article text), write these fields. Use ONLY facts present in the provided text — never invent details, numbers, or precedents.

Keep it TIGHT — this is a glimpse meant to spark curiosity, not an essay. Every field is ONE short sentence; prefer concrete over flowery.

- "i": the item's number <n>, copied exactly, so it can be matched back.
- "topic": the single best subject tag from EXACTLY this list — quantum, chips, ai, robotics, nuclear, energy, defense, bio, launch, satellite, exploration, astronomy, manufacturing, mining, materials, geology, cleanenergy, ecosystems, water, weather, climate, society, policy, other. Use "cleanenergy" for renewables/solar/wind/grid-battery good news; "ecosystems" for wildlife/biodiversity/conservation; "water" for oceans/rivers/freshwater; "weather" for meteorology / forecasting science; "climate" ONLY for a serious, major climate development; "energy" for grids/electricity/helium-3/fusion-for-power; "nuclear" for reactors/SMRs; "society" for social & human-impact stories; "policy" for government/institutional/regulatory power; "defense" for defense TECHNOLOGY.
- "country": ISO-2 code of the primary organization's home country (e.g. US, CN, JP, IN, DE, FR, GB, AU, CA, KR, TW, NL, RU), or "" if unclear/multinational.
- "headline": a short, vivid, accurate title (max ~80 chars).
- "scifi_hook": ONE punchy sentence (<= 22 words) capturing the wonder / novelty — cinematic but strictly real. The "whoa, we live in the future" line that also conveys what happened. (e.g. "A company is manufacturing medicine in orbit and parachuting it back to the desert.")
- "eli5": ONE simple sentence (<= 22 words) explaining it like the reader is smart but brand-new — unpack any jargon (ISRU, qubit, rare-earth, polyhalite, etc.).
- "why": ONE short sentence (<= 18 words) on why it matters for the real world / balance of power.
- "tickers": array of affected ticker symbols FROM THE WATCHLIST. Put EVERY applicable symbol here — including a nearest read-through (e.g. RKLB, LMT) when the key company is itself private. Do NOT name tickers only in prose. If truly nothing in the watchlist is relevant, use [].
- "proxy_note": ONLY when the key company is private/unlisted — one short clause naming it (e.g. "SpaceX is private"). Otherwise "".
- "bias": "up" | "down" | "mixed" | "n/a" — likely directional read-through for the tickers (speculative).
- "rationale": a SHORT clause (<= 10 words) on the market read-through (speculative). No price targets. If no watchlist ticker is affected, use "".
- "confidence": "low" | "medium" | "high" — your confidence in the market read-through.

Rules:
- Every sentence must be defensible from the article text.
- Keep each field to ONE sentence. No markdown, no bullet characters inside fields.
- The market read-through is speculative and must never be phrased as advice.
- For "climate" items: stay sober and factual — no wonder framing, no alarmism, no doom. It is shown as a single line, so make "why" a calm, precise statement of what changed and why it's important.
- For other "earth" items (cleanenergy, ecosystems, water, weather): let the wonder be about the living planet — a species recovering, a reef regrowing, a cleaner grid — not just markets.

Return ONLY JSON: {"items":[{"i":<n>, "topic":"...", "country":"...", ...one object per input item...}]}"""


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

    # Match analyses to items by their echoed index — NOT by array position —
    # so a reordered/short model response can never attach text to the wrong link.
    by_i = {}
    for r in results:
        try:
            by_i[int(r["i"])] = r
        except (KeyError, ValueError, TypeError):
            continue
    if not by_i and results:  # model omitted indices; fall back to input order
        by_i = dict(enumerate(results))

    for idx, c in enumerate(flat):
        a = by_i.get(idx, {})
        c["headline"] = a.get("headline") or c["title"]
        c["topic"] = a.get("topic", "")
        c["country"] = a.get("country", "")
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
    c["topic"] = {"space": "launch", "minerals": "mining", "tech": "quantum",
                  "earth": "ecosystems", "society": "policy"}.get(c["_theme"], "other")
    c["country"] = "JP"
    c["scifi_hook"] = "The sci-fi part: this is real and happening right now (mock)."
    c["eli5"] = "In plain terms: a simple explanation for a newcomer (mock)."
    c["why"] = "Why it matters: it nudges the real world in a concrete way (mock)."
    c["proxy_note"] = ""
    c["tickers"] = {"space": ["RKLB"], "tech": ["IONQ"], "minerals": ["MP"]}.get(c["_theme"], [])
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


# Small subject icon per item so the topic is clear at a glance.
TOPIC_EMOJI = {
    "quantum": "🪄", "chips": "⛵️", "ai": "🔮", "robotics": "🤖", "nuclear": "🔅",
    "energy": "⚡️", "defense": "🌐", "bio": "🧬", "launch": "🚀", "satellite": "🪐",
    "exploration": "🪐", "astronomy": "🔭", "manufacturing": "🏭", "mining": "💎",
    "materials": "💎", "geology": "💎", "society": "🌳", "policy": "🌐",
    # Living Earth
    "cleanenergy": "🌱", "ecosystems": "🦋", "water": "💧", "weather": "🌤",
    "climate": "🌡️", "other": "🔹",
}


def iso_flag(iso):
    """ISO-2 country code -> flag emoji ('' if unknown)."""
    iso = (iso or "").strip().upper()
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)


# State-controlled outlets — matched by source name OR domain (whether they came
# from a dedicated feed or surfaced via Google News). Items from these get a clear
# "pinch of salt" label: reliable for the OFFICIAL position, not neutral analysis.
STATE_MEDIA = {
    "chinadaily": "CN", "china daily": "CN", "cgtn": "CN", "xinhua": "CN",
    "global times": "CN", "globaltimes": "CN", "people's daily": "CN",
    "peoplesdaily": "CN", "people.cn": "CN", "china.org": "CN", "ecns": "CN",
    "gmw.cn": "CN", "guangming": "CN", "stdaily": "CN", "cas.cn": "CN",
    "scio.gov": "CN", "news.cn": "CN",
    "rt.com": "RU", "russia today": "RU", "tass": "RU", "sputnik": "RU",
    "ria novosti": "RU",
}


def state_media_iso(item):
    """Return ISO-2 of the state outlet if this item is from one, else ''."""
    hay = ((item.get("source") or "") + " " + (item.get("link") or "")).lower()
    for key, iso in STATE_MEDIA.items():
        if key in hay:
            return iso
    return ""


def _px(v):
    return f"{v:.0f}" if v >= 100 else f"{v:.2f}"


def fmt_market_line(item, prices):
    """Compact market line — returns '' when no watchlist ticker applies, so
    pure-wonder items stay short (no 'no proxy' clutter)."""
    parts = []
    for t in item.get("tickers", []):
        p = prices.get(t)
        parts.append(f"<code>{esc(t)}</code> ${_px(p['last'])}" if p
                     else f"<code>{esc(t)}</code>")
    if not parts:
        return ""
    arrow = {"up": "↗", "down": "↘", "mixed": "↔"}.get(item.get("bias", "n/a"), "")
    lead = f"{arrow} " if arrow else ""
    rationale = (item.get("rationale") or "").strip().rstrip(".")
    reason = f" — {esc(rationale)}" if rationale else ""
    return f"› <b>Market:</b> {lead}{' · '.join(parts)}{reason}"


def format_item(item, prices):
    num = f"{item['n']}. " if item.get("n") else ""
    topic = item.get("topic", "")
    tag = TOPIC_EMOJI.get(topic, "")
    flag = iso_flag(item.get("country", ""))
    prefix = " ".join(x for x in (flag, tag) if x)
    prefix = f"{prefix} " if prefix else ""
    # A bare ⚠️ before the line = state-controlled outlet; read with a pinch of salt.
    warn = "⚠️ " if state_media_iso(item) else ""
    lines = [f"▸ {warn}{prefix}<b>{num}{esc(item.get('headline'))}</b>"]
    # Climate flags are rendered sober and SHORT — one supporting line, no hype.
    if topic == "climate":
        note = item.get("why") or item.get("eli5") or item.get("scifi_hook")
        if note:
            lines.append(f"› {esc(note)}")
        if item.get("link"):
            href = html.escape(item["link"], quote=True)
            lines.append(f"› <a href=\"{href}\">{esc(item['source'])} ↗</a>")
        return "\n".join(lines)
    if item.get("scifi_hook"):
        lines.append(f"› <b>The sci-fi part:</b> {esc(item['scifi_hook'])}")
    if item.get("eli5"):
        lines.append(f"› <b>In plain terms:</b> {esc(item['eli5'])}")
    if item.get("why"):
        lines.append(f"› <b>Why it matters:</b> {esc(item['why'])}")
    market = fmt_market_line(item, prices)
    if market:
        lines.append(market)
    if item.get("link"):
        href = html.escape(item["link"], quote=True)
        lines.append(f"› <a href=\"{href}\">{esc(item['source'])} ↗</a>")
    return "\n".join(lines)


def build_theme_messages(analyzed, prices, date_str):
    """Return a list of (theme, message_text) chunks, each under the TG limit."""
    messages = []
    for theme, meta in THEMES.items():
        items = analyzed.get(theme)
        if not items:
            continue
        header = (f"<b>{esc(meta['title'])}</b>\n"
                  f"<i>{esc(meta['tagline'])}</i>")
        current = header
        for it in items:
            block = format_item(it, prices)
            candidate = current + "\n\n" + block
            if len(candidate) > TELEGRAM_LIMIT:
                messages.append((theme, current))
                current = (f"<b>{esc(meta['title'])}</b> "
                           f"<i>(cont.)</i>\n\n" + block)
            else:
                current = candidate
        messages.append((theme, current))
    return messages


# ----------------------------------------------------------------------------
# 7. Send
# ----------------------------------------------------------------------------

def _send_one(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"[telegram] {chat_id} error {r.status_code}: {r.text}")
            return False
        return True
    except Exception as e:
        print(f"[telegram] {chat_id} failed: {e}")
        return False


def send_telegram(text):
    """Send to your private DM plus any EXTRA_CHATS (channel/group for friends).
    Success is judged on the primary DM; extras are best-effort."""
    if DRY_RUN:
        print("\n" + "=" * 64)
        print(text)
        print("=" * 64)
        return True
    primary_ok = True
    for i, chat in enumerate([TELEGRAM_CHAT_ID] + EXTRA_CHATS):
        if not chat:
            continue
        ok = _send_one(chat, text)
        if i == 0:
            primary_ok = ok
        time.sleep(0.4)  # gentle with per-chat rate limits
    return primary_ok


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
                "n": c.get("n"),
                "theme": theme, "topic": c.get("topic"), "country": c.get("country"),
                "headline": c.get("headline"), "title": c["title"],
                "scifi_hook": c.get("scifi_hook"), "eli5": c.get("eli5"),
                "why": c.get("why"), "tickers": c.get("tickers"),
                "proxy_note": c.get("proxy_note"), "bias": c.get("bias"),
                "rationale": c.get("rationale"), "confidence": c.get("confidence"),
                "link": c["link"], "source": c["source"],
                "text": (c.get("text") or "")[:1500],  # grounding for "deeper"
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

    # Number items globally (in THEME order, same order persist writes them) so the
    # reply bot's "deeper N" references line up with what's shown.
    n = 0
    for t in THEMES:
        for c in analyzed.get(t, []):
            n += 1
            c["n"] = n

    all_t = [t for items in analyzed.values() for c in items for t in c.get("tickers", [])]
    prices = fetch_prices(all_t)

    messages = build_theme_messages(analyzed, prices, date_str)
    fact = CONTEXT_FACTS[_now().timetuple().tm_yday % len(CONTEXT_FACTS)]
    lead = (f"🛰️ <b>REALITY SCI-FI CHECK</b> — <i>{date_str}</i>\n"
            f"🌐 <i>{esc(fact)}</i>\n\n"
            f"<i>{len(messages)} dispatches. Reply</i> <code>more tech</code> / "
            f"<code>deeper 3</code> / <code>players space</code> <i>to dig in.</i>")
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
