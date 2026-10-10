# Marser

**Commerce & Market Intelligence, assembled live from SerpApi.**

Marser takes three inputs — a company, its website, and its category — and returns a
source-linked **market briefing**: who the company is, whether its market is still expanding or
already saturated, who it competes with and at what price, what the marketplace and finance
signals say, where the risks are, and what a buyer or analyst should still go and ask.

Every external fact in that briefing comes from **SerpApi**. Nothing else touches the network.

> Built for the **SerpApi India Hackathon 2026** · Track: **Commerce & Market Intelligence**
> *"Turn product, price, merchant, finance, trend, and marketplace results into useful tools for
> shoppers, sellers, analysts, or small businesses."*

---

## How Marser answers the problem statement

The track asks for product, price, merchant, finance, trend, and marketplace results turned into
something useful. Marser consumes all six, each from its own SerpApi engine, and fuses them into
one decision document:

| The track asks for | Marser's SerpApi source | What it becomes in the briefing |
| --- | --- | --- |
| **Product** | `google_play` | App listings, ratings, review counts — is there a shipped product, and do people rate it? |
| **Price** | `google_shopping` + 4× `google` *"pricing plans"* | A side-by-side price read on the company **and three named competitors** |
| **Merchant** | `google_shopping` (`source` / seller field) | Which merchants actually carry the product, and at what spread |
| **Finance** | `google_finance` | A year of share price for the company's own listing, or for a listed stand-in when it is private |
| **Trend** | `google_trends` | A 12-month interest timeline for the company *against its whole category* — the saturation read |
| **Marketplace** | `google_shopping`, `google_play` | Marketplace presence and positioning, not just a homepage claim |

Surrounding those: `google` for the company, its founders and its competitor set, `google_news`
for funding and category momentum, and `google_jobs` for a hiring signal that gets classified in
code into an engineering / ML / sales role mix.

**Who it's for.** The analyst sizing up a company before a meeting — at a fund, a corporate
development team, or a small business deciding whether to enter or buy into a category. It is the
work of an afternoon of tab-switching, done in about a minute, with every claim clickable.

---

## Where SerpApi is used

SerpApi is not *a* data source in Marser — it is *the* data source. One module,
[`app/serp_client.py`](app/serp_client.py), is the only code in the repository permitted to make an
outbound request, and it only ever calls `https://serpapi.com/search.json`. There is no scraping,
no second vendor, and no model-supplied fact anywhere in the pipeline.

### Seven engines, eighteen searches, two waves

Every briefing runs exactly these eighteen searches.

| No. | Wave | SerpApi engine | Query | Feeds |
| --- | --- | --- | --- | --- |
| 1 | 1 | `google` | `{company} {category}` | Company summary, risks |
| 2 | 1 | `google` | `{company} founder OR co-founder OR CEO` | Company summary |
| 3 | 1 | `google` | `{company} competitors alternatives` | Competitors |
| 4 | 1 | `google` | `{company} pricing plans` | **Price** |
| 5 | 1 | `google_news` | `{company}` | Company summary, risks |
| 6 | 1 | `google_news` | `{company} funding OR raises OR investors` | Company summary |
| 7 | 1 | `google_news` | `{category}` | Market, competitors |
| 8 | 1 | `google_jobs` | `{company}` | Hiring signal (role mix) |
| 9 | 1 | `google_trends` | `{company},{category}` | **Trend** — market saturation |
| 10 | 1 | `google_play` | `{company}` | **Product** |
| 11 | 1 | `google_shopping` | `{company}` | **Price, merchant, marketplace** |
| 12 | 2 | `google` | `{competitor_1} pricing plans` | **Price** (competitive) |
| 13 | 2 | `google` | `{competitor_2} pricing plans` | **Price** (competitive) |
| 14 | 2 | `google` | `{competitor_3} pricing plans` | **Price** (competitive) |
| 15 | 2 | `google_finance` | `{subject_ticker}`, `window=1Y` | **Finance** — the stock chart |
| 16 | 2 | `google` | `{company} market share percent {category}` | Industry share figures |
| 17 | 2 | `google` | `{company} brand value OR valuation OR "valued at"` | Brand value figures |
| 18 | 2 | `google_news` | `{company} market share OR brand value OR valuation` | Both of the above |

**Wave 1** (searches 1–11) runs all eleven concurrently. Its results go to an LLM *entity call*
whose only job is to name three competitors, say whether the company is itself listed, and name
any publicly listed comparable — all from what the evidence actually says. **Wave 2** (searches
12–18) then searches SerpApi again for those freshly discovered entities, so the competitive price
read and the stock chart are chosen by the data, not hardcoded.

Searches 16–18 exist because **SerpApi has no engine that returns a market share or a brand
valuation**. Those numbers only exist in what somebody published, so they are fetched as ordinary
web and news results and read off the evidence by the analysis call under the same rule as every
other claim: a figure appears on screen only if a cited source stated it. Where nothing stated
one, the chart says so rather than drawing an estimate.

A search that errors or returns nothing yields zero evidence and a status of `error` or `empty`.
The pipeline never raises on thin data; the briefing just carries fewer citations, and the search
log on screen shows exactly which engine came up short.

### SerpApi fields Marser reads past the snippet

Most of the pipeline turns each engine's results into uniform text evidence. Two engines carry
numbers that text would throw away, so [`app/series.py`](app/series.py) pulls them straight out of
the raw SerpApi response and ships them to the UI as charts:

- **`google_trends`** → the `interest_over_time` timeline: 12 months of company-vs-category
  interest, drawn as the market-saturation graph.
- **`google_finance`** → the price `graph` over a `1Y` window, thinned to 120 points. The panel
  only captions it as the company's own listing when the symbol that came back matches the one
  the entity call asked for; otherwise it is labelled a stand-in.

`google_shopping` is read for `price`, `extracted_price`, `source` (the merchant) and `rating`;
`google_play` for `rating`, `reviews` and `price`; `google_finance` for `summary.price`,
`price_change`, `price_change_percent` and `market_cap`. See
[`app/normalizers.py`](app/normalizers.py) — one function per engine.

---

## The governing rule: no uncited claims

The hard part of market intelligence is not gathering results, it is not quietly inventing things
between them. Marser's rule is absolute:

> **SerpApi is the only source of external facts. The LLM reasons only over evidence items and
> must cite every statement by evidence ID. A statement whose citations don't resolve is deleted
> before the briefing is ever saved.**

That is enforced in code, not in a prompt:

- Every normalized result becomes an **evidence item** with a stable ID (`e01`, `e02`, …), a
  registrable source domain, and a resolved publication date.
- [`app/validator.py`](app/validator.py) walks the model's output and drops any evidence ID that
  isn't in the evidence map — and drops the whole statement if nothing valid survives.
- **Confidence is computed, not claimed.** A statement may only be marked `Corroborated` if its
  citations span **two distinct registrable domains** with headlines that aren't near-duplicates
  (`SequenceMatcher` ratio < 0.8). Everything else is downgraded to `Single source`.
- The **hiring role mix is computed in Python**, not by the model, from the `google_jobs` titles,
  then handed to the analysis call as settled fact so the prose cannot contradict the number on
  screen.

The result: every line in the briefing is clickable back to the SerpApi result that produced it,
and "Corroborated" means something you can check.

---

## What the briefing contains

- **Scorecard** — Team, Traction, Market, Defensibility, Risk, each scored 1–5 with a cited rationale
- **Company summary** and key facts
- **Market read** — expanding or saturated, against the `google_trends` category timeline
- **Competitors and pricing** — the competitor set and their price points
- **Three market charts** — the share price over a year from `google_finance`; industry share and
  brand value over time, both built only from figures a cited source actually stated
- **News highlights** and trajectory
- **Risks**, by category
- **Diligence checklist** — what the evidence already settled (Found / Partial) and the questions
  that remain genuinely open, ranked by priority and de-duplicated

---

## Setup

```bash
uv venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux

uv pip install -r requirements.txt
cp .env.example .env           # then fill in your keys
```

### Environment variables

| Variable | Purpose |
| --- | --- |
| `SERPAPI_API_KEY` | Your SerpApi key. Required unless `REPLAY_MODE=true`. |
| `GROQ_API_KEY` | Your Groq key (console.groq.com). Required unless `REPLAY_MODE=true`. |
| `LLM_MODEL` | Groq model id used for both LLM calls, e.g. `openai/gpt-oss-120b`. |
| `LLM_TOKENS_PER_MINUTE` | Your Groq plan's TPM for that model (default `8000`, the on-demand tier figure). Both LLM calls are paced against this rolling window. |
| `LLM_PROMPT_TOKEN_BUDGET` | Token ceiling for the analysis prompt (default `5200`). |
| `LLM_ENTITY_PROMPT_TOKEN_BUDGET` | Token ceiling for the entity prompt (default `2200`). |
| `SEARCH_BUDGET` | Live SerpApi searches allowed before requests return HTTP 429. |
| `REPLAY_MODE` | `true` to serve only saved briefings — no API keys, no network calls. |

### Staying inside Groq's token window

Groq meters tokens per rolling minute, and the limit covers a single request as well as
the minute: on the on-demand tier `openai/gpt-oss-120b` allows 8,000, so a prompt above
that is refused outright with `413 Request too large` — no retry can fix it, only a
smaller prompt. Two things keep the run inside that window:

- **Each prompt is fitted before it is sent.** `app/prompts.py` trims the evidence block
  — fewer results per search, shorter snippets — until the whole prompt is under its
  budget, keeping at least one readable item from every search. If Groq still refuses a
  request as too large, `app/analyzer.py` reads the limit out of the error and rebuilds
  the prompt against it instead of resending.
- **The two calls are paced.** `app/analyzer.py` tracks tokens spent over the last sixty
  seconds and holds the next call until it fits, which is cheaper than letting it come
  back `429` and waiting out a blind backoff.

On a plan with a larger allowance, raise `LLM_TOKENS_PER_MINUTE` and the two prompt
budgets together — more budget means more evidence reaches the model and a denser
briefing.

## Run

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`, enter a company, its website and its category, and click
**Generate**. A live progress bar tracks the run over server-sent events while the eighteen
searches go out. The header shows SerpApi searches spent and budget remaining at all times.

### API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/briefing` | Full pipeline, one JSON response — for programmatic callers |
| `GET /api/briefing/stream` | Same pipeline as server-sent events, `{progress, label}` per step |
| `GET /api/briefings` | List saved briefings |
| `GET /api/briefings/{id}` | Fetch one saved briefing |
| `GET /api/usage` | `{live_searches, budget, remainder, replay_mode}` |

---

## Protecting SerpApi credits

A build that burns its search quota on the third demo is not a usable tool, so credit discipline is
part of the architecture:

- **Content-addressed cache.** Every SerpApi request is keyed by the SHA-256 hash of the engine
  plus its sorted parameters, excluding `api_key`. A cache hit never expires and costs nothing — so
  re-running the same company, or replaying a demo, spends **zero** searches.
- **Hard budget ceiling.** A SQLite counter increments on every *live* request. At `SEARCH_BUDGET`,
  `BudgetExceeded` is raised **before any network call is attempted** and the API returns HTTP 429.
  You cannot overspend by accident.
- **Tests never go live.** The HTTP layer is mocked and reads from `tests/fixtures/`, which holds
  one real raw SerpApi response per search.

### Seeding real fixtures

The first time you point Marser at a real company, capture its SerpApi responses once so later runs
and tests don't spend live searches:

```bash
python scripts/capture_fixtures.py --company "ExampleAI" --website "https://example.ai" --category "AI legal assistant"
```

This writes one raw response per search to `tests/fixtures/`. All later development reads from the
cache or those fixtures.

### Tests

```bash
pytest
```

162 tests, no live requests.

---

## Replay Mode

Set `REPLAY_MODE=true` to run Marser with **no API keys and no network access** — useful for
demoing on flaky wifi, or for reviewing output without spending a search.

```bash
REPLAY_MODE=true uvicorn app.main:app --reload
```

In this mode `POST /api/briefing` returns the saved briefing whose company name matches the request
(case-insensitive), and HTTP 404 when none matches. Saved briefings live in `saved_briefings/`, one
JSON file each, written automatically by every live run — so whatever has already been generated is
what replays.

---

## Project layout

```
marser/
  app/
    main.py            FastAPI app and the six endpoints
    planner.py         builds the 18 SerpApi searches, in two waves
    serp_client.py     the ONLY module that calls SerpApi; cache and budget
    normalizers.py     one function per engine, raw SerpApi response to evidence
    series.py          trends timeline and finance price graph, for the charts
    evidence.py        evidence schema, IDs, source domains, staleness
    roles.py           job-title classification for the hiring signal
    analyzer.py        the entity call and the analysis call
    prompts.py         both prompts and the output JSON schema
    validator.py       citation check, confidence rules, diligence ranking
    pipeline.py        the ten steps
    storage.py         SQLite cache + usage counter, saved briefings
    static/index.html  the UI
  scripts/
    capture_fixtures.py
  tests/
    fixtures/          one raw SerpApi response per search
  saved_briefings/
  data/                marser.db — SerpApi response cache and usage counter
  .env.example
  requirements.txt
  README.md
```

## Stack

FastAPI · SQLite (stdlib `sqlite3`) · httpx · Groq for the two LLM calls · a single
dependency-free HTML page for the UI · **SerpApi for every external fact.**
