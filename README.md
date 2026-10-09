# PitchScout

PitchScout turns a startup's name into a source-linked pre-pitch briefing for an investment
analyst. Enter a company name, website, and category; PitchScout runs 16 SerpApi searches,
turns the results into evidence items, and returns one briefing led by a five-dimension
scorecard, followed by a company summary, a market read (saturated or still expanding?),
competitors and pricing, risks, a short list of top questions to ask the founders, and a gap
checklist — every statement links back to the source it came from.

Built for the **SerpApi India Hackathon 2026**, track Commerce & Market Intelligence.

**Who it's for:** the analyst or associate at a VC fund, angel network, or corporate venture
team who prepares the brief before a pitch meeting.

**Governing rule:** SerpApi is the only source of external facts. The LLM reasons only over
evidence items and cites every statement by evidence ID. A statement without a valid
evidence ID is removed before the briefing is saved.

## Search plan

Every briefing runs exactly these 16 searches across seven SerpApi engines.

| No. | Wave | Engine | Query | Feeds |
| --- | --- | --- | --- | --- |
| 1 | 1 | `google` | `"{company}" {category}` | Company summary, risks |
| 2 | 1 | `google` | `"{company}" founder OR co-founder OR CEO` | Company summary |
| 3 | 1 | `google` | `{company} competitors alternatives` | Competitors |
| 4 | 1 | `google` | `{company} pricing plans` | Commercial |
| 5 | 1 | `google_news` | `"{company}"` | Company summary, risks |
| 6 | 1 | `google_news` | `"{company}" funding OR raises OR investors` | Company summary |
| 7 | 1 | `google_news` | `{category}` | Market, competitors |
| 8 | 1 | `google_jobs` | `{company}` | Company summary (hiring signal) |
| 9 | 1 | `google_trends` | `{company},{category}` | Market |
| 10 | 1 | `google_play` | `{company}` | Commercial |
| 11 | 1 | `google_shopping` | `{company}` | Commercial |
| 12 | 2 | `google` | `{competitor_1} pricing plans` | Commercial |
| 13 | 2 | `google` | `{competitor_2} pricing plans` | Commercial |
| 14 | 2 | `google` | `{competitor_3} pricing plans` | Commercial |
| 15 | 2 | `google_finance` | `{ticker_1}` | Commercial, competitors |
| 16 | 2 | `google_finance` | `{ticker_2}` | Commercial, competitors |

Wave 1 (searches 1–11) runs concurrently, feeds an LLM entity call that proposes three
competitors and two publicly listed comparable companies, then wave 2 (searches 12–16) runs
against those entities. A search that errors or returns nothing produces zero evidence and a
status of `error` or `empty`; the pipeline never raises on empty data.

## Setup

```bash
uv venv
.venv\Scripts\activate        # Windows
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
| `SEARCH_BUDGET` | Live SerpApi searches allowed per month before requests return HTTP 429. |
| `REPLAY_MODE` | `true` to serve only the saved demo briefings, with no API keys and no network calls. |

## Run

```bash
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/`. Enter a company, its website, and its category, and click
**Generate** — a live progress bar tracks the run over `GET /api/briefing/stream` (server-sent
events) while `POST /api/briefing` does the same work as a single JSON response for
programmatic callers. The page opens with the scorecard, then the company summary, market
read, competitors and pricing, risks, top questions (collapsed to the 5-6 most important, with
a "Show more" for the rest), and a gap checklist — every statement links back to its cited
source.

### Seeding real fixtures

The first time you point PitchScout at a real company, capture its SerpApi responses once so
later runs and tests don't spend live searches:

```bash
python scripts/capture_fixtures.py --company "ExampleAI" --website "https://example.ai" --category "AI legal assistant"
```

This writes one raw response per search to `tests/fixtures/`. All later development reads from
the cache (which never expires) or those fixtures.

### Tests

```bash
pytest
```

Tests never make live requests — the HTTP layer is mocked and reads from `tests/fixtures/`.

## Replay Mode

Set `REPLAY_MODE=true` to run PitchScout with no API keys and no network access. In this mode,
`POST /api/briefing` returns the saved briefing whose company name matches the request
(case-insensitive) and HTTP 404 when none matches. The repository ships with three such
briefings in `saved_briefings/`:

- **Acme AI** — AI legal research assistant
- **Nimbus Health** — AI clinical documentation assistant
- **Fernbank** — B2B expense management SaaS

```bash
REPLAY_MODE=true uvicorn app.main:app --reload
```

> **Note on these three seed briefings:** this environment had no live `SERPAPI_API_KEY`
> available, so they were produced by running the real pipeline, evidence,
> role-mix, and validator code unmodified against representative SerpApi-shaped input and a
> small deterministic stand-in for the two LLM calls (grounded only in the evidence those
> inputs produced, so every citation is still real and still passes the validator). Run
> `capture_fixtures.py` against a real company and generate a briefing with real keys and
> `REPLAY_MODE=false` to replace any of them with a genuine live run.

## Project layout

```
pitchscout/
  app/
    main.py            FastAPI app and the five endpoints
    planner.py         builds the 16 searches
    serp_client.py     the only module that calls SerpApi; cache and budget
    normalizers.py     one function per engine, raw response to evidence items
    evidence.py        evidence schema, IDs, name filter, staleness
    roles.py           job title classification
    analyzer.py        entity call and analysis call
    prompts.py         both prompts and the output JSON schema
    validator.py       citation check, confidence rules, question count
    pipeline.py        the ten steps
    storage.py         SQLite and saved briefings
    static/index.html  the UI
  scripts/
    capture_fixtures.py
  tests/
    fixtures/          one raw SerpApi response per search
  saved_briefings/
  data/
  .env.example
  requirements.txt
  README.md
```

## Credit protection

- Every SerpApi request goes through `serp_client.search()`, cached by the SHA-256 hash of the
  engine plus its sorted parameters (excluding `api_key`). A cache hit never expires and spends
  nothing.
- A SQLite counter increments on every live request. At `SEARCH_BUDGET`, further live requests
  raise `BudgetExceeded` and the API returns HTTP 429.
- Tests never make live requests.
