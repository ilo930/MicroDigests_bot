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
        system_prompt = """You are a cynical market analyst tracking energy storage and grid infrastructure.

INCLUDE an item if it contains ANY of these:
- Investment over $10 million (Capital Deployment)
- Regulatory filing or policy change (Regulatory Change)
- Supply constraint or shortage (Supply Shock)
- Grid interconnection or transmission update (Technical Setup)

For each item that qualifies, output EXACTLY this format:

🚀 <strong>Headline here</strong>
<b>Signal</b> Capital Deployment / Regulatory Change / Supply Shock / Technical Setup
<b>Why it matters</b> One sentence
<b>Context</b> Like X in YYYY or "No clear precedent"
<b>Action</b> Buy on pullback / Watch / Take profits / Avoid / Hedge

Then ONE empty line between items.

If you are unsure whether to include an item, INCLUDE it. Better to send a false positive than miss a signal.

Use emojis: 🚀 Space, ⚡ Energy Grid, 🔋 Storage, 🏛️ Policy

Keep response under 3500 characters."""

    else:
        system_prompt = """You are a space launch tracker.

Extract ALL rocket launches mentioned.

Output EXACTLY this format with NO extra blank lines inside each launch:

🚀 Launch: Rocket name
<b>Payload</b> What was launched
<b>Date</b> Date or "Upcoming"

Then ONE empty line between launches.

If no launches found, output: "No launches in today's news."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these news items. Include ALL that qualify:\n{news_text}"}
        ],
        "temperature": 0.1
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error"
    
    return result["choices"][0]["message"]["content"]

def send_to_telegram(message):
    if not message or len(message) < 10:
        return
    
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
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
        print("Getting high-signal analysis...")
        signal_analysis = analyze_with_groq(raw_news, "signal")
        
        print("Getting launch log...")
        launch_log = analyze_with_groq(raw_news, "launch")
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        
        # Send signal digest
        header = f"🟢 S I G N A L   D I G E S T   {today}\n\n"
        send_to_telegram(header + signal_analysis)
        
        # Send launch log
        launch_header = f"🚀 L   A   U   N   C   H   L   O   G   {today}\n\n"
        send_to_telegram(launch_header + launch_log)
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
