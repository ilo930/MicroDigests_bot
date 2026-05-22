import feedparser
import requests
import os

from google import genai

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=GEMINI_API_KEY)

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
            print(f"Error: {e}")
    return "\n".join(all_entries[:10])

def summarize_with_gemini(news_text):
    prompt = f"Summarize these news headlines in 3 bullet points with emojis:\n{news_text}"
    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt
    )
    return response.text

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)

if __name__ == "__main__":
    raw_news = fetch_news()
    if raw_news:
        summary = summarize_with_gemini(raw_news)
        send_to_telegram(f"📡 Daily Digest:\n\n{summary}")
        print("Sent")
    else:
        send_to_telegram("No news today")
        print("No news")
