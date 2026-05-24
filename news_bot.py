import feedparser
import requests
import os
import re
import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_FEEDS = [
    "https://arstechnica.com/space/feed/",
    "https://spaceflightnow.com/feed/",
    "https://www.energy-storage.news/feed/",
    "https://www.utilitydive.com/feeds/news/",
]

def fetch_news():
    all_entries = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title_lower = entry.title.lower()
                noise_keywords = ['podcast', 'video', 'interview', 'opinion', 'philosophical']
                if any(kw in title_lower for kw in noise_keywords):
                    continue
                all_entries.append(f"• {entry.title}\n  {entry.link}")
        except Exception as e:
            print(f"Error with {feed_url}: {e}")
    return "\n\n".join(all_entries[:25])

def analyze_with_groq(news_text):
    system_prompt = """You are a market analyst. Analyze EVERY news item.

For EACH item, output EXACTLY this format:

🔋 HEADLINE IN ALL CAPS
Signal: Capital Deployment / Regulatory Change / Supply Shock / Technical Setup / Routine Update
Why: One sentence
Context: "No clear precedent" or a real example
Action: Aggressive Buy / Buy on pullback / Watch / Take profits / Avoid / Ignore

Use emojis: 🔋 for battery/solar, ☀️ for renewables, 🏛️ for policy, 🚀 for space, 🔬 for materials

Keep response under 4000 characters."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze:\n{news_text}"}
        ],
        "temperature": 0.1
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error"
    
    return result["choices"][0]["message"]["content"]

def filter_ignore_items(text):
    """Remove any item that has 'Action: Ignore' in it"""
    lines = text.split('\n')
    result = []
    skip_until_next_emoji = False
    
    for line in lines:
        if 'Action: Ignore' in line:
            skip_until_next_emoji = True
            continue
        if skip_until_next_emoji and ('🔋' in line or '☀️' in line or '🏛️' in line or '🚀' in line or '🔬' in line):
            skip_until_next_emoji = False
        if not skip_until_next_emoji:
            result.append(line)
    
    return '\n'.join(result)

def extract_launches(news_text):
    launches = []
    lines = news_text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        if ('launch' in line_lower or 'starship' in line_lower or 'falcon' in line_lower) and '•' in line:
            headline = line.split('•')[1].strip()
            if headline not in launches:
                launches.append(headline)
                if len(launches) >= 5:
                    break
    
    if not launches:
        return "No launches in today's news."
    
    result = []
    for launch in launches[:5]:
        result.append(f"🚀 {launch}")
        result.append("")
    
    return '\n'.join(result)

def send_to_telegram(message):
    if not message or len(message) < 10:
        return
    
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram error: {response.text}")
        else:
            print("Sent successfully")
    except Exception as e:
        print(f"Failed to send: {e}")

if __name__ == "__main__":
    print("Fetching news...")
    raw_news = fetch_news()
    
    if raw_news and len(raw_news) > 50:
        print("Getting analysis...")
        analysis = analyze_with_groq(raw_news)
        
        # Filter out Ignore items
        analysis = filter_ignore_items(analysis)
        
        # Extract launches separately
        launch_log = extract_launches(raw_news)
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        
        header = f"🟢 SIGNAL DIGEST {today}\n\n"
        send_to_telegram(header + analysis)
        
        launch_header = f"🚀 LAUNCH LOG {today}\n\n"
        send_to_telegram(launch_header + launch_log)
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
