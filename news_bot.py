import feedparser
import requests
import os

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_FEEDS = [
    # Space (gold standard only)
    "https://payloadspace.com/feed/",
    "https://arstechnica.com/space/feed/",
    
    # Energy (tech + bureaucracy)
    "https://www.energy-storage.news/feed/",
    "https://www.electrive.com/feed/",
    "https://www.ferc.gov/rss-feed/ferc-news.xml",
    "https://www.energy.gov/articles/feed",
    
    # Crypto (on-chain data)
    "https://coinglass.com/feed",
]

def fetch_news():
    all_entries = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                all_entries.append(f"• {entry.title}\n  {entry.link}")
        except Exception as e:
            print(f"Error: {e}")
    return "\n\n".join(all_entries[:15])

def summarize_with_groq(news_text):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": """You are a cynical market analyst. Apply these rules STRICTLY:

FIRST, delete ANY item that does NOT contain:
- A regulatory filing (FAA, FCC, FERC, DOE, SEC)
- A multi-million dollar capital move ($10M+)
- An on-chain metric (funding rate, liquidation, OI)
- A launch license or reentry permit
- A grid interconnection queue update

If an item is about:
- BMW hydrogen parts
- Bolt EV ride-hailing
- Price prediction articles
- Philosophical "what to save from ISS" stories
- Routine operational updates with no capital or regulatory change

→ DELETE it entirely. Do not summarize it. Do not give it a "No Signal" label. Just skip it.

For items that SURVIVE, output EXACTLY this format:

<b>[EMOJI] HEADLINE</b>
<b>Signal:</b> [Surprise Catalyst / Sell the News / Regulatory Delay / Short Squeeze Setup]
<b>Why it matters:</b> [one sentence]
<b>History:</b> [If you know: "Similar to X in YYYY → Z% over N weeks". If not: "No clear precedent"]
<b>Action:</b> [Buy on pullback / Hold / Watch / Take profits / Exit / Add to watchlist]

Use emojis: 🚀 Space, ⚡ Energy, 📊 Crypto, 🔵 Tech, 🏛️ Regulation

Be direct. No fluff. No explanations. If nothing survives, output exactly: "No actionable signals today." """},
            {"role": "user", "content": f"Apply the deletion filter first, then analyze only the survivors:\n{news_text}"}
        ],
        "temperature": 0.1
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    return result["choices"][0]["message"]["content"]

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, json=payload)

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    raw_news = fetch_news()
    if raw_news:
        summary = summarize_with_groq(raw_news)
        send_to_telegram(f"📡 Daily Digest:\n\n{summary}")
        print("News sent")
    else:
        send_to_telegram("No news fetched today")
        print("No news")
