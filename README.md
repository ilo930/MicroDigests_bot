# Reality Sci-Fi Check

A Telegram digest about the future arriving. Every three days it posts seven
things genuinely happening in **space, critical minerals, frontier tech** and
the **living Earth** — each written so someone new to the field can follow it,
each keeping its source link.

**→ [Subscribe on Telegram: @cosmic_spill](https://t.me/cosmic_spill)** · free,
no ads.

## What a story looks like

```
▸ 🇮🇳 ⛏ Rajasthan signs India's first rare-earth exploration licence
› The sci-fi part: India begins its own hunt for rare-earth minerals in Rajasthan.
› In plain terms: The state issued the country's first permit to explore rare earths.
› Why it matters: A step toward domestic supply of critical minerals for tech.
› ETGovernment.com ↗
```

## Talk back to it

The channel is one half. Message the bot and it answers from the digest it just
sent:

| | |
|---|---|
| `deeper 6` | Expand story 6 — more detail, and what to read next |
| `players 6` | Who's behind story 6: companies, agencies, countries |
| `more space` | A few more fresh stories from one section |
| `menu` | Everything it can do |

## How it works

News is pulled from named publisher feeds (Spaceflight Now, SpaceNews, NASA,
ESA, JAXA, Ars Technica, Mining.com, The Quantum Insider, Phys.org, plus India
and Asia desks). A language model picks the seven most surprising and writes the
three plain-English lines. It never invents a number: share prices are attached
in code from market data, and only for tickers on a fixed watchlist. Chinese and
Russian state outlets are included deliberately and always flagged ⚠️.

The whole thing runs free on GitHub Actions — a cron every three days for the
digest, and a rolling listener for replies. There is no server.

## Running it yourself

```bash
python3 smoke_test.py                       # is it still alive? sends nothing
MOCK_LLM=1 DRY_RUN=1 python3 news_bot.py    # build a digest, print it, send nothing
```

Sending for real needs `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and
`GROQ_API_KEY`, which live as GitHub repository secrets. No key is in the code.

The shape of the project, the decisions behind it and the known rough edges are
in [ARCHITECTURE.md](ARCHITECTURE.md).
