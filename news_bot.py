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
            {"role": "system", "content": "Summarize news in 3 bullet points with emojis. No fluff. Be direct."},
            {"role": "user", "content": f"Summarize these headlines:\n{news_text}"}
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
