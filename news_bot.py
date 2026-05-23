import feedparser
import requests
import os
import re
import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# FIXED: Working RSS feeds only
RSS_FEEDS = [
    # Space
    "https://arstechnica.com/space/feed/",
    "https://spaceflightnow.com/feed/",
    
    # Energy storage & grid
    "https://www.energy-storage.news/feed/",
    "https://www.utilitydive.com/feeds/news/",
    "https://www.eia.gov/electricity/feed/",
    
    # Policy & regulation (working endpoints)
    "https://www.energy.gov/articles/feed",
    "https://www.eia.gov/petroleum/feed/",
    
    # Critical minerals
    "https://www.benchmarkminerals.com/feed/",
    
    # Crypto on-chain (working)
    "https://cointelegraph.com/rss/tag/funding-rate",
]

# FIXED: Better feed fetching with fallbacks
def fetch_news():
    all_entries = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:  # Check for parsing errors
                print(f"Warning: {feed_url} parsed with errors")
            for entry in feed.entries[:5]:  # Increased to 5 per feed
                # Filter out obvious noise by title
                title_lower = entry.title.lower()
                noise_keywords = ['podcast', 'video', 'interview', 'price prediction', 
                                 'opinion', 'what to save', 'philosophical']
                if any(kw in title_lower for kw in noise_keywords):
                    continue
                all_entries.append(f"• {entry.title}\n  {entry.link}")
        except Exception as e:
            print(f"Error with {feed_url}: {e}")
    return "\n\n".join(all_entries[:20])  # More items for better context

def summarize_with_groq(news_text):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": """You are a cynical market analyst tracking energy, space, and crypto infrastructure.

For EACH news item, classify and output EXACTLY this format:

<b>[EMOJI] HEADLINE</b>
<b>Signal:</b> [Capital Deployment / Regulatory Change / Supply Shock / Technical Setup / No Signal]
<b>Why it matters:</b> [1 sentence explaining actual market impact]
<b>Context:</b> [If similar happened before: "Like X in YYYY". If not: "First instance of this"]
<b>Action:</b> [Buy on pullback / Watch / Take profits / Avoid / Hedge]

Use emojis: 🚀 Space, ⚡ Energy Grid, 🔋 Storage, 🏛️ Policy, 📊 Crypto, 🔬 Materials

CRITICAL: Do NOT filter items out. Every item gets analyzed. If an item is truly noise (opinion piece, price prediction, routine update), label it "No Signal" with action "Ignore".

Be direct. No introductions. No fluff.

IMPORTANT: Keep your entire response under 3800 characters total."""},
            {"role": "user", "content": f"Analyze each news item:\n{news_text}"}
        ],
        "temperature": 0.2
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    # Error handling for Groq API
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error - check your Groq key or usage limits"
    
    return result["choices"][0]["message"]["content"]

def send_to_telegram(message):
    # Truncate to Telegram's 4096 character limit
    if len(message) > 4096:
        message = message[:4000] + "\n\n... (truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram error: {response.text}")
        else:
            print("Telegram sent successfully")
    except Exception as e:
        print(f"Failed to send: {e}")

if __name__ == "__main__":
    print("Fetching news...")
    raw_news = fetch_news()
    
    if raw_news and len(raw_news) > 50:
        print(f"Found {len(raw_news.split('•'))-1} items. Sending to Groq...")
        summary = summarize_with_groq(raw_news)
        
        # ADDED: Print Groq output to logs so you can see it
        print(f"\n=== GROQ OUTPUT ===\n{summary}\n=== END GROQ OUTPUT ===\n")
        
        send_to_telegram(f"📡 Daily Digest - {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n{summary}")
        print("News sent")
    else:
        print("No news fetched")
        send_to_telegram(f"📡 Daily Digest - {datetime.datetime.now().strftime('%Y-%m-%d')}\n\nNo actionable news fetched today. Check RSS feeds.")
