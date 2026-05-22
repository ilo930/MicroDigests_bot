import feedparser
import requests
import os

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_FEEDS = [
    "https://payloadspace.com/feed/",
    "https://spaceflightnow.com/feed/",
    "https://www.energy-storage.news/feed/",
    "https://www.faa.gov/news/updates/?feed=news",
    "https://www.electrive.com/feed/",
    "https://cointelegraph.com/rss",
    "https://arstechnica.com/space/feed/",
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
            {"role": "system", "content": """You are a financial news analyst. For each news item, provide:

1. Summary (one sentence)
2. Signal type: Choose from [Surprise Catalyst, Sell the News, No Signal, Regulatory Delay, Short Squeeze Setup, Liquidation Risk]
3. Historical pattern: Reference 1-2 similar past events and what happened next (price move % and time frame)
4. Action suggestion: One of [Buy on pullback, Hold, Watch, Take profits, Exit, Add to watchlist]

Format each item exactly as:
📡 [HEADLINE]
Summary: [one sentence]
Signal: [type]
History: [past example with % and time]
Action: [one word or short phrase]

Be direct. No fluff. No disclaimer."""},
            {"role": "user", "content": f"Analyze these news items for signals, patterns, and actions:\n{news_text}"}
        ],
        "temperature": 0.3
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    return result["choices"][0]["message"]["content"]

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
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
