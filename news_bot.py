import feedparser
import requests
import os
import re
import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# --- THE TELEMETRY PIPELINE ---
# These are no longer general news feeds. These are raw agency endpoints.
RSS_FEEDS = [
    # 1. Raw Federal Register FAA Space Telemetry
    "https://www.federalregister.gov/api/v1/documents.rss?conditions[agencies][]=federal-aviation-administration&conditions[term]=space",
    # 2. Raw FCC Electronic Document Feed (STAs, Satellite tracking)
    "https://www.fcc.gov/feeds/edocs.xml",
    # 3. Raw FERC Daily Filings and Grid Queue Reforms
    "https://elibrary.ferc.gov/eLibrary/rss/whatsnew",
    # 4. Raw Dept of Energy (DOE) Loan and Policy Releases
    "https://www.energy.gov/api/v1/news.rss",
    # 5. Core Institutional Policy Analysis (The Filtered Exception)
    "https://payloadspace.com/feed/",
    "https://www.energy-storage.news/feed/"
]

def fetch_news():
    all_entries = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:6]:  
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
        system_prompt = """You are an asymmetric macro intelligence analyst tracking space policy bottlenecks and power grid regulation. Your core objective is to analyze regulatory filings, agency updates, and institutional policy shifts to issue high-conviction proxy calls 14 days before mainstream financial media identifies the trend.

### CRITICAL COGNITIVE PROTOCOLS
1. SPOT THE REACTION GAP: Look specifically for regulatory gatekeeping. An approved FAA Launch License, an FCC Special Temporary Authority (STA) grant, a FERC cluster queue reform, or a Department of Energy (DOE) conditional loan guarantee are high-impact catalysts.
2. REVENUE IMPACT: Distinguish between minor procedural paperwork and massive structural unlocks. (e.g., A streamlined "One-Stop" Office of Space Commerce certification speeds up time-to-market for payload operators like $PL or $SPIR; an oversubscribed CAISO/ERCOT interconnection cluster delay traps capital for grid integrators like $FLNC).
3. PROXIES ONLY: Explicitly connect agency decisions to public tickers: Space ($RKLB, $SPIR, $PL), Grid ($FLNC, $TSLA, $GEV), Hydrogen ($PLUG, $BE). 
4. MECHANICAL DIFFERENTIATION: You must distinguish between a new capital buildout (which drives physical hardware procurement) and a portfolio acquisition/asset flip (which is a secondary market paper transfer and does not create immediate hardware demand). If an item is an asset transfer, explicitly state that it yields zero immediate hardware revenue.
5. STRICT BAN ON REPETITIVE PHRASES: Do not use boilerplate or lazy repetitive text across entries.

### THE BLAST RADIUS RULE
You are forbidden from stating "Private" or "No direct trade." You must use the ecosystem mapping provided below to link private sector adjustments directly to public proxy stocks.

### HARDCODED ECOSYSTEM & ASYMMETRIC DYNAMICS MAPPING
- Space Launch Capacity / Bottlenecks / Policy -> Rocket Lab ($RKLB), Spire Global ($SPIR), Planet Labs ($PL).
  *CRITICAL MACRO DYNAMIC:* SpaceX Starship milestones are competitive headwinds (-) for Rocket Lab ($RKLB) launch services, but serve as massive cost-reduction tailwinds (+) for satellite constellation operators/components providers like Spire ($SPIR) or Planet Labs ($PL) due to cheaper ride-share costs.
- Grid Infrastructure / Texas ERCOT / BESS / Storage Deployment -> Fluence Energy ($FLNC), Tesla ($TSLA), GE Vernova ($GEV).
- Hydrogen Production / Industrial Infrastructure -> Plug Power ($PLUG), Bloom Energy ($BE).

### FORMATTING OUTPUT REQUIREMENT
For each high-signal regulatory or bottleneck shift, output EXACTLY this format:

<strong>🏛️ REGULATORY SIGNAL: [GOVERNMENT AGENCY / REGULATOR]</strong>
<b>Ecosystem Catalyst:</b> [FAA Part 450 / FCC STA / FERC Queue Reform / DOE 45V Voucher / Infrastructure Grant]
<b>The Shift:</b> One hyper-specific sentence on what policy or timeline changed based strictly on the text.
<b>Public Proxies (Blast Radius):</b> Tickers from your cheat sheet with a (+) or (-) indicator.
<b>The Asymmetric Alpha:</b> Explain the 14-day lead. Why does a delay or approval here drastically alter the cash flow or time-to-market for the public proxy before retail notices?
<b>Tactical Stance:</b> Accumulate / Hedge / Watch + Precise operational trigger condition.

Filter ruthlessly. If an entry does not contain a specific regulatory shift, an institutional funding milestone, or a structural grid bottleneck update, output nothing."""

    else:
        system_prompt = """You are an orbital launch tracker.
Extract active rocket launches mentioned.

Output EXACTLY this format:
<b>Launch:</b> Rocket name
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
        "temperature": 0.0  
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
        
        header = f"<b>E C O S Y S T E M  D I G E S T</b> ｜ {today}\n\n"
        send_to_telegram(header + signal_analysis)
        
        launch_header = f"<b>L A U N C H  L O G</b> ｜ {today}\n\n"
        send_to_telegram(launch_header + launch_log)
        
        print("Done")
    else:
        send_to_telegram(f"No news fetched on {datetime.datetime.now().strftime('%Y%m%d')}")
        print("No news")
