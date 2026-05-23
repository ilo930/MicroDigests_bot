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

def analyze_with_groq(news_text, analysis_type):
    if analysis_type == "signal":
        system_prompt = """You are a cynical market analyst. 

CRITICAL: If an item has NO actionable market impact, DO NOT include it. Skip it completely.

For items that SURVIVE, output EXACTLY this format:

<strong>🚀 Headline here</strong>
<strong>Signal:</strong> Capital Deployment / Regulatory Change / Supply Shock / Technical Setup
<strong>Why it matters:</strong> One sentence
<strong>Context:</strong> Like X in YYYY or "No clear precedent"
<strong>Action:</strong> Buy on pullback / Watch / Take profits / Avoid / Hedge

Then a blank line, then next item.

Use emojis: 🚀 Space, ⚡ Energy, 🔋 Storage, 🏛️ Policy

NEVER output "No Signal" or "Ignore". Omit those items entirely.

If EVERY item is noise, output exactly: "No high-signal items today."

Keep response under 3500 characters."""

    else:  # launch log
        system_prompt = """You are a space launch tracker.

Extract ONLY routine rocket launches (SpaceX, Rocket Lab, ULA, etc.).

Output EXACTLY this format:

<strong>🚀 Launch: Rocket name</strong>
<strong>Payload:</strong> What was launched
<strong>Date:</strong> Date or "Upcoming"

Then a blank line, then next launch.

If no launches found, output: "No launches in today's news.""

Keep response under 2000 characters."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these news items:\n{news_text}"}
        ],
        "temperature": 0.2
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error"
    
    return result["choices"][0]["message"]["content"]

def send_to_telegram(message, topic=None):
    if not message or len(message) < 10:
        return
    
    # Remove any malformed HTML and ensure <strong> tags are balanced
    message = re.sub(r'</?b>', '<strong>', message)  # Replace <b> with <strong>
    message = re.sub(r'</?strong>', '<strong>', message)
    
    # Ensure all <strong> tags are closed
    open_count = message.count('<strong>')
    close_count = message.count('</strong>')
    if open_count > close_count:
        message += '</strong>' * (open_count - close_count)
    
    # Truncate if too long
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram error: {response.text}")
        else:
            print(f"Sent {topic or 'message'} successfully")
    except Exception as e:
        print(f"Failed to send: {e}")

if __name__ == "__main__":
    print("Fetching news...")
    raw_news = fetch_news()
    
    if raw_news and len(raw_news) > 50:
        print("Getting high-signal analysis...")
        signal_analysis = analyze_with_groq(raw_news, "signal")
        
        print("Getting launch log...")
        launch_log = analyze_with_groq(raw_news, "launch")
        
        # Send both messages
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        if signal_analysis and signal_analysis != "No high-signal items today.":
            send_to_telegram(f"📡 SIGNAL DIGEST {today}\n\n{signal_analysis}", "signal")
        else:
            send_to_telegram(f"📡 SIGNAL DIGEST {today}\n\nNo high-signal items today.", "signal")
        
        if launch_log and launch_log != "No launches in today's news.":
            send_to_telegram(f"🚀 LAUNCH LOG {today}\n\n{launch_log}", "launch")
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y-%m-%d')}")
        print("No news")
