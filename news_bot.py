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
            for entry in feed.entries[:6]:  # Pull slightly more to ensure high-signal coverage after filtering
                title_lower = entry.title.lower()
                noise_keywords = ['podcast', 'video', 'interview', 'opinion', 'philosophical', 'roundup']
                if any(kw in title_lower for kw in noise_keywords):
                    continue
                all_entries.append(f"• {entry.title}\n  {entry.link}")
        except Exception as e:
            print(f"Error with {feed_url}: {e}")
    return "\n\n".join(all_entries[:30])

def analyze_with_groq(news_text, analysis_type):
    if analysis_type == "signal":
        system_prompt = """You are an asymmetric macro intelligence analyst evaluating energy grid infrastructure and space markets. Your job is to translate raw industry events into actionable ecosystem proxy trades.

### ANTI-HALLUNCIATION & COGNITIVE RULES
1. STICK STRICTLY TO THE TEXT: You are forbidden from inventing features, technologies, locations, or byproducts that are not explicitly cited in the input headlines. If a solar/storage article does not explicitly say it produces hydrogen, DO NOT map it to the hydrogen ecosystem.
2. BAN BOILERPLATE: Do not copy and paste the same repetitive generic reasoning across different items. Every "Asymmetric Angle" must focus entirely on the unique real-world mechanics of that exact headline (e.g., call out specific state bills, corporate names, or regional grid conditions).
3. NO FABRICATIONS: If you do not know a specific piece of data or historical connection with absolute certainty, do not guess or invent it.

### THE BLAST RADIUS RULE
You are forbidden from stating "Private" or "No direct trade." You must use the ecosystem mapping provided below to link private sector capital expansions, infrastructure upgrades, or regulatory bottlenecks directly to public proxy stocks.

### HARDCODED ECOSYSTEM MAPPING
- Space Launch Capacity / Bottlenecks / Policy -> Rocket Lab ($RKLB), Spire Global ($SPIR), Planet Labs ($PL).
- Grid Infrastructure / Texas ERCOT / BESS / Storage Deployment -> Fluence Energy ($FLNC), Tesla ($TSLA), GE Vernova ($GEV).
- Hydrogen Production / Industrial Infrastructure -> Plug Power ($PLUG), Bloom Energy ($BE).

### CONDITIONAL FILTERING RULE
Evaluate every article against these explicit core concepts: [FAA/FCC Launch License, Interconnection Queue, FERC Ruling, DOE Loan, PPA, Capacity Bottleneck]. If an entry is simply generic consumer PR, a historical feature, or cannot be directly tied to the financial blast radius of these public proxies, DROP IT ENTIRELY. Do not output anything for it.

### FORMATTING OUTPUT REQUIREMENT
For each valid item that qualifies, output EXACTLY this format:

<strong>📡 SIGNAL: [INSERT CORPORATE ENTITY OR AGENCY]</strong>
<b>Glossary Match:</b> [Insert specific term match from list above]
<b>The Vector:</b> One clear sentence explaining the physical shift or capital movement.
<b>Public Proxies (Blast Radius):</b> List explicit tickers from the cheat sheet with a (+) for bullish or (-) for bearish.
<b>The Asymmetric Angle:</b> Explain the structural connection between this event and the public stock's upcoming revenue or bottleneck relief. Why will retail miss this?
<b>Tactical Stance:</b> Accumulate / Hedge / Watch + Short trigger condition.

Put EXACTLY ONE blank line between items. Do not invent metrics or prices if you do not know them."""

    else:
        system_prompt = """You are an orbital launch tracker.
Extract active rocket launches mentioned.

Output EXACTLY this format:
🚀 <b>Launch:</b> Rocket name
<b>Payload:</b> What was launched
<b>Date:</b> Date or "Upcoming"

Then ONE empty line between launches.
If no launches found, output: "No launches in today's news.\""""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these news items. Filter heavily and output only high-signal events:\n{news_text}"}
        ],
        "temperature": 0.0  # Dropped to absolute minimum to eliminate hallucination creativity
    }
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if "error" in result:
        print(f"Groq API error: {result}")
        return "⚠️ API error"
    
    return result["choices"][0]["message"]["content"]

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
    
    # Cap strictly below Telegram's 4096 character markdown/HTML rendering crash zone
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (truncated due to length rules)"
    
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
        print("Getting high-signal ecosystem analysis...")
        signal_analysis = analyze_with_groq(raw_news, "signal")
        signal_analysis = clean_spacing(signal_analysis)
        
        print("Getting launch log...")
        launch_log = analyze_with_groq(raw_news, "launch")
        launch_log = clean_spacing(launch_log)
        
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        header = f"🟢 <b>E C O S Y S T E M  D I G E S T</b> ｜ {today}\n\n"
        send_to_telegram(header + signal_analysis)
        
        launch_header = f"🚀 <b>L A U N C H  L O G</b> ｜ {today}\n\n"
        send_to_telegram(launch_header + launch_log)
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
