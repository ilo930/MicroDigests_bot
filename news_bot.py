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
                all_entries.append(f"• {entry.title}")
        except Exception as e:
            print(f"Error with {feed_url}: {e}")
    return "\n".join(all_entries[:20])

def analyze_with_groq(news_text):
    system_prompt = """You are a market analyst. Analyze each news item.

For each item, output EXACTLY this plain text format with NO bold, NO HTML, NO markdown:

[EMOJI] HEADLINE
Signal: TYPE
Why: ONE SENTENCE
Context: SPECIFIC PRECEDENT or "No clear precedent"
Action: BUY/WATCH/AVOID
Public Proxies: $TICKER, $TICKER (max 3)

Then ONE blank line before next item.

Use these emojis:
🔋 = battery/storage
☀️ = solar/renewable
🏛️ = policy/regulation
🚀 = space/rocket
🔬 = materials/supply

Signal types: Capital Deployment, Regulatory Change, Supply Shock, Technical Setup

Actions: Aggressive Buy, Buy on pullback, Watch, Take profits, Avoid

Public Proxies: List relevant stock tickers that would be impacted.

Example:
🔋 SPEARMINT ENERGY SECURES $450M
Signal: Capital Deployment
Why: Large BESS investment in Texas
Context: Similar to 2024 Spearmint Texas deal
Action: Buy on pullback
Public Proxies: $FLNC, $TSLA, $STEM

Keep response under 3500 characters. NO bold. NO HTML. Plain text only."""

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
        return "API error"
    
    return result["choices"][0]["message"]["content"]

def clean_formatting(text):
    # Remove any remaining markdown or bold markers
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    # Remove numbering
    text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
    # Remove intro lines
    lines = text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines):
        if '🔋' in line or '☀️' in line or '🏛️' in line or '🚀' in line or '🔬' in line:
            start_idx = i
            break
    text = '\n'.join(lines[start_idx:])
    # Ensure exactly one blank line between items
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def send_to_telegram(message):
    if not message or len(message) < 10:
        return
    
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (truncated)"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    
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
        analysis = clean_formatting(analysis)
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        
        send_to_telegram(f"SIGNAL DIGEST {today}\n\n{analysis}")
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
