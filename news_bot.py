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
    # Only used for signal analysis now
    system_prompt = """You are a cynical market analyst tracking energy storage and grid infrastructure.

For each item, choose the CORRECT emoji based on sector:
- 🔋 Battery storage or grid infrastructure
- ☀️ Solar, wind, or renewable generation
- 🏛️ Policy, regulation, or legislation
- 🚀 Space, rockets, or satellites (ONLY for non-launch space news)
- 🔬 Supply chains, materials, or critical minerals

Then output EXACTLY this format:

<strong><em>🔋 HEADLINE TEXT IN ALL CAPS HERE</em></strong>
<b>Signal</b> Capital Deployment / Regulatory Change / Supply Shock / Technical Setup
<b>Why it matters</b> One sentence
<b>Context</b> Real example or "No clear precedent"
<b>Action</b> Aggressive Buy / Buy on pullback / Watch / Take profits / Avoid

CRITICAL RULES:
- ONE blank line between items
- NEVER duplicate headlines
- NEVER use 🚀 for energy or storage items

Keep response under 3500 characters."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these news items:\n{news_text}"}
        ],
        "temperature": 0.1
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error"
    
    return result["choices"][0]["message"]["content"]

def extract_launches(news_text):
    # Simple pattern matching for launch headlines (no AI)
    launches = []
    lines = news_text.split('\n')
    
    for line in lines:
        line_lower = line.lower()
        # Look for space/launch related headlines
        if ('launch' in line_lower or 'starship' in line_lower or 'falcon' in line_lower) and '•' in line:
            headline = line.split('•')[1].strip()
            # Remove duplicates
            if headline not in launches:
                launches.append(headline)
    
    if not launches:
        return "No launches in today's news."
    
    # Format output
    result = []
    for launch in launches[:10]:
        result.append(f"🚀 Launch: {launch}")
        result.append("<b>Payload</b> See article link")
        result.append("<b>Date</b> Today's news")
        result.append("")  # Empty line between launches
    
    return '\n'.join(result)

def clean_spacing(text):
    if not text:
        return text
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    cleaned = '\n'.join(lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned

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
        signal_analysis = clean_spacing(signal_analysis)
        
        print("Extracting launches locally...")
        launch_log = extract_launches(raw_news)
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        
        header = f"🟢 S I G N A L   D I G E S T   {today}\n\n"
        send_to_telegram(header + signal_analysis)
        
        launch_header = f"🚀 L   A   U   N   C   H   L   O   G   {today}\n\n"
        send_to_telegram(launch_header + launch_log)
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
