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
            for entry in feed.entries[:2]:
                all_entries.append(f"• {entry.title}")
        except Exception as e:
            print(f"Error fetching {feed_url}: {e}")
    return "\n".join(all_entries[:10])

def summarize_with_groq(news_text):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": """You are a financial news analyst. For each news item, output EXACTLY this format using HTML tags:

<b>[EMOJI] TITLE</b>
<b>Signal:</b> [Surprise Catalyst / Sell the News / Regulatory Delay / Short Squeeze Setup / No Signal]
<b>Why it matters:</b> [one sentence]
<b>History:</b> [past example with % and time frame]
<b>Action:</b> [Buy / Hold / Watch / Take profits / Exit / Add to watchlist]

Use these emojis by domain:
🚀 Space
⚡ Energy
📊 Crypto
🔵 Tech
🏛️ Regulation

No extra text. No explanations. No fluff. Each item exactly 5 lines."""},
            {"role": "user", "content": f"Analyze these news items:\n{news_text}"}
        ],
        "temperature": 0.3
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
