# Architecture

## What this project is

A Telegram digest called **Reality Sci-Fi Check**: every three days it gathers
news about space, critical minerals, frontier tech and the living Earth, has a
language model write three plain-English lines per story, and posts the result
to the channel **@cosmic_spill**. A second bot answers messages (`deeper 6`,
`players 6`, `more space`) using the digest it just sent. Everything runs free
on GitHub Actions — there is no server.

## Style

**Pipeline.** News enters, passes through fetch → dedup → select → analyse →
prices → format → send → persist, and a message comes out. Each stage hands its
result to the next and knows nothing about the others.

The **landing page under `site/versions/` is not part of that pipeline** and does
not share its style. Each page is a self-contained trio — one HTML, one
stylesheet, one script — that opens by double-clicking, with no server and no
build step. That constraint is deliberate: the user opens these from Finder.

## Map

| File | What it does |
|---|---|
| `news_bot.py` | The whole digest pipeline, in eight numbered sections: feeds, dedup, LLM selection, LLM analysis, prices, formatting, sending, saving state |
| `watchlist.py` | The fixed list of tickers the digest is allowed to cite |
| `players.py` | Who's who behind a story — companies, agencies, countries |
| `reply_core.py` | Turns an incoming message into replies; reuses `news_bot.py` so answers sound like the digest |
| `poller.py` | The live listener: long-polls Telegram for ~5.5h per run and answers via `reply_core` |
| `api/telegram.py` | A Vercel webhook wrapper over `reply_core` (superseded — see rough edges) |
| `state/seen.json` | Stories already sent, so nothing repeats |
| `state/latest_digest.json` | The last digest, written only after a real send — the reply bot and the smoke test both read it |
| `.github/workflows/news-bot.yml` | The cron that sends the digest every three days, then commits `state/` back |
| `.github/workflows/reply-bot.yml` | Keeps exactly one listener alive around the clock |
| `site/index.html` | The original plain page: what the channel is, and the subscribe link |
| `site/versions/framed.html` + `.css` + `.js` | The landing page, cute-mouse version. Markup, look, behaviour in three files |
| `site/versions/framed-mascot02.html` + `.css` + `.js` | Same page, grumpy-mouse version |
| `site/versions/_mascots/` | The two mascots on their own, SVG plus CSS, so either page can be rebuilt from them |
| `site/verify_pages.py` | The one command that says whether both pages are still intact |
| `smoke_test.py` | The one command that says whether it all still works |

## How to run it

```bash
python3 smoke_test.py     # is it still alive? posts nothing, costs nothing
python3 site/verify_pages.py   # are both landing pages still intact?
git pull                  # the deployed bot commits state/ — pull before reading it locally

DRY_RUN=1 python3 news_bot.py    # build a real digest, print it, send nothing
MOCK_LLM=1 DRY_RUN=1 python3 news_bot.py   # same, without spending LLM credit
```

Sending for real happens only in GitHub Actions, which holds `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID` and `GROQ_API_KEY` as repository secrets. No key is in the
code, and `.env` is gitignored.

## Decisions

Newest first.

- The landing page keeps **one self-contained trio per version** rather than a
  shared base plus overrides. Sharing would remove real duplication, but these
  pages are opened straight from Finder and a broken relative path would leave a
  blank screen with no clue why.
- The coffee button picks one of three palettes **once per page load**, never
  mid-session, and `?palette=mint|gum|lilac` forces one for screenshots.
- Two transforms must never share an element in the mascot: `.eye` owns the
  blink, `.gaze` owns the look direction. A CSS animation silently beats an
  inline style, so putting both on `.eye` kills the gaze with no error.
- Superseded designs are moved to `~/claude-corbeille/`, never deleted. Seven
  other page designs and four prototype folders went there on 2026-08-04.

- The smoke test judges liveness from the **published** `state/latest_digest.json`
  on GitHub, not the local copy — this laptop's clone is usually weeks behind,
  and the question is whether the deployed bot is running.
- The smoke test forces `DRY_RUN` and `MOCK_LLM` before importing `news_bot`, so
  a check can never post to the channel or spend credit.
- Replies use long-polling (`poller.py`) rather than the webhook: GitHub throttles
  frequent crons, which made webhook-era replies feel dead.
- Analyses are matched to stories by an echoed index, never by array position, so
  a reordered model response cannot attach text to the wrong link.
- Prices are fetched in code from market data and only for watchlist tickers, so
  the model can never invent a number.
- State media (Chinese, Russian) is included deliberately and always labelled ⚠️.

## Known rough edges

- `news_bot.py` is ~970 lines, well past the point where it would normally be
  split into one file per pipeline stage. It has clean internal section
  boundaries, so the split is straightforward — it just has not been done, and
  the bot is in daily use, so it is a change to make deliberately.
- `api/telegram.py` and `vercel.json` are the earlier webhook path, superseded by
  `poller.py`. They are kept rather than removed, but nothing runs them today.
- The smoke test cannot check Telegram from this laptop — the token lives only in
  GitHub secrets, so that one check reports as skipped.
- The two page stylesheets are ~90% identical (~340 lines each) and both sit
  above the 200-line split point. There is a real boundary inside them — tokens,
  frame, mascot — so both the split and the de-duplication are straightforward;
  neither has been done.
- Both page scripts contain `if (eye) ...`, which does nothing and says nothing
  when the element is missing. A silent no-op, and it should log instead.
- `verify_pages.py` reads the files; it never opens a browser. It catches a
  broken page, not an ugly one.

