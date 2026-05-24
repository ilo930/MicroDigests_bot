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
    system_prompt = """You are a market analyst. Analyze EVERY news item below. Do not skip anything.

For EACH item, output EXACTLY this format:

<strong><em>🔋 HEADLINE TEXT IN ALL CAPS HERE</em></strong>
<b>Signal</b> Capital Deployment / Regulatory Change / Supply Shock / Technical Setup / Routine Update
<b>Why it matters</b> One sentence
<b>Context</b> "No clear precedent" or a real example
<b>Action</b> Aggressive Buy / Buy on pullback / Watch / Take profits / Avoid / Ignore

Use these emojis:
- 🔋 Battery storage or grid
- ☀️ Solar or renewables
- 🏛️ Policy or regulation
- 🚀 Space or rockets
- 🔬 Supply chains or materials

CRITICAL: You MUST output something for every headline. If truly nothing matters, write "Routine Update" as Signal and "Ignore" as Action.

Keep response under 3500 characters."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze EVERY news item. Output something for each one:\n{news_text}"}
        ],
        "temperature": 0.1
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    # DEBUG: Print the full response to logs
    print(f"DEBUG Groq response status: {response.status_code}")
    print(f"DEBUG Groq result keys: {result.keys() if result else 'None'}")
    
    if "error" in result:
        print(f"DEBUG Groq error: {result['error']}")
        return "⚠️ API error - check Groq key"
    
    if "choices" not in result or len(result["choices"]) == 0:
        print(f"DEBUG Unexpected response: {result}")
        return "⚠️ No choices in response"
    
    content = result["choices"][0]["message"]["content"]
    print(f"DEBUG Groq content length: {len(content)} characters")
    print(f"DEBUG Groq first 200 chars: {content[:200]}")
    
    return content

def extract_launches(news_text):
    # Simple pattern matching for launch headlines (no AI) - max 5 items
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
                if len(launches) >= 5:  # Stop after 5 items
                    break
    
    if not launches:
        return "No launches in today's news."
    
    # Format output
    result = []
    for launch in launches[:5]:  # Ensure max 5
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
        print(f"DEBUG Signal analysis received: {bool(signal_analysis)}")
        if signal_analysis:
            print(f"DEBUG First 100 chars: {signal_analysis[:100]}")
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
