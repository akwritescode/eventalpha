# Examples

Calling the EventAlpha API and following its live stream. `API` is
`http://localhost:8081` locally (`make up`) or your deployment's URL.

## Demo data

```bash
make up && make seed      # fills every panel of the web UI with clearly labelled demo items
```

[`demo-data.sql`](demo-data.sql) only loads into an empty warehouse. To remove it again:

```sql
BEGIN;
DELETE FROM article_scores WHERE model = 'demo:model';
DELETE FROM x_leads WHERE post_id IN ('99000000000000000001', '99000000000000000002', '99000000000000000003');
DELETE FROM articles WHERE source_id LIKE 'demo-%';
DELETE FROM insider_transactions WHERE accession LIKE 'demo-%';
DELETE FROM econ_events WHERE event_key LIKE 'demo-%';
DELETE FROM earnings_events WHERE source = 'demo';
DELETE FROM signals WHERE message LIKE '%(demo)%';
DELETE FROM ticker_universe WHERE ticker IN ('DEMOA', 'DEMOB', 'DEMOC');
COMMIT;
```

## Move explanation

The **Ask EventAlpha** panel takes a question such as “Why did NVDA move in the last 30 minutes?”
or just a ticker. `POST /api/v1/move-query` turns the question into a ticker and a window:
Claude (`EVENTALPHA_ASK_MODEL`, default `claude-haiku-5-5`) fills a fixed JSON schema through
structured outputs, and the API checks the ticker against `ticker_universe` and that the window has
ended and is at most seven days long before the browser calls `move-explanation`. A bare ticker skips the
model and offers time-frame chips: the last 30 minutes, hour or two hours, today, since
yesterday's close, or a custom range (any past start and end up to seven days apart, picked in
one range field). Follow-ups such as “What was known by then?” reuse the window
on screen and replay it as of its end.

“Today” uses the New York regular session from the exchange calendar, ending at the current minute
or the session close. Closed days and mornings before the open receive a clear message. “Since
yesterday” starts at the previous trading session’s close, skipping closed calendar days, so these
windows may span weekends, up to seven days. Minute-bar collection covers the combined Nasdaq-100
and S&P 500 membership plus benchmarks. Custom-range pickers use the browser's time zone, and
requests carry UTC timestamps.

Without `ANTHROPIC_API_KEY` the endpoint answers free text with 503 and the chat asks for a ticker
instead. Questions that reach the model are limited to `EVENTALPHA_ASK_RATE_LIMIT_PER_MINUTE`
(default 10) per IP, on top of the API's global limit.

After `make seed`, start the web app with `cd web && REACT_APP_API_URL=http://localhost:8081 npm start`.
In **Ask EventAlpha**, type `NVDA`, choose **Custom…** and pick April 15, 2025, 5:20 to 5:35 p.m. ET
(entered in your browser's time zone). The demo uses NVIDIA's
[April 15, 2025 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000082/nvda-20250409.htm)
with its actual EDGAR acceptance time. The X post IDs and EventAlpha observation and review times
are simulated. The X links in this fixture are placeholders. The selected window is illustrative,
and the read API can replay stored evidence.

Then ask “What was known by then?” to see what the fixture makes available by
5:35 p.m. ET. The 5:29 p.m. discovery was first seen at 5:37 p.m. and the unverified 5:40 p.m.
lead was published after the window. Both appear in the retrospective timeline.

```bash
API=http://localhost:8081
curl -fsS -G "$API/api/v1/tickers/NVDA/move-explanation" \
  --data-urlencode 'start=2025-04-15T17:20:00-04:00' \
  --data-urlencode 'end=2025-04-15T17:35:00-04:00' \
  --data-urlencode 'asOf=2025-04-15T17:35:00-04:00' | jq .data
```

Omit `asOf` for a retrospective view. Both window boundaries count as during. The timeline looks
one day on either side, and labels timing by publication. Replays also consult first-seen and
verification times. An article edited after the cutoff is omitted because the warehouse retains
only its current version. Sources published before or during the window can contribute to a
plausible catalyst when a reviewed discovery published by the end links to them. Multiple
discoveries for the same original article count as one catalyst.

Material, company-specific SEC filings and PR Newswire releases can qualify on their own. Replay uses the latest eligible
JEV score through the cutoff and excludes scores that predate the visible article version.

For index constituents, unpause or trigger `market_move_bars` with `TRADIER_BROKER_KEY` configured. The first
run requests eight days of regular-session one-minute bars for every collected symbol. The API uses
the close of the last completed candle before the start and at or before the end. It reports
actual measurement and observation times when collection lags or the market is closed. Series
without a valid opening observation are omitted. Candles first collected after a replay cutoff
are excluded. Minute-bar prices are unavailable for the historical demo fixture.

For a manual review, follow the link cited by the post and read the original. The
`eventalpha.sources.x` boundary accepts the post ID, ticker, publication time and a short
reviewer-written paraphrase via `record_lead`. If the original confirms the claim and is present
in `articles`, call `verify_lead` with its source key and a supporting passage from the article.
The boundary matches the passage against the article, pins the decision to that version and
keeps X leads outside the article classification pipeline.

## REST (curl)

```bash
API=http://localhost:8081
curl -s "$API/api/v1/feed?types=sec,news&limit=5" | jq '.data[] | {label, title, tickers}'
curl -s "$API/api/v1/feed?ticker=NVDA&days=30" | jq '.data | length'
curl -s "$API/api/v1/signals/latest" | jq '.data[] | {signalType, score, confidence}'
curl -s "$API/api/v1/calendar/upcoming?days=7" | jq '.data.earnings[:5]'
curl -s "$API/api/v1/events?type=guidance_lowered&minProb=0.8" | jq '.data[].title'
```

Paging the feed: pass the last item's `occurredAt` and `id` back as `before` and `beforeId`.

```bash
last=$(curl -s "$API/api/v1/feed?limit=20" | jq -r '.data[-1] | "\(.occurredAt) \(.id)"')
curl -s "$API/api/v1/feed?limit=20&before=${last% *}&beforeId=${last#* }" | jq '.data[].id'
```

## Live stream (Server-Sent Events)

`stream=events` carries high-impact events (the ones posted to Telegram); `stream=feed`
announces every new item in the stream. Reconnecting clients resume from the last event ID.

```bash
curl -N "$API/api/v1/stream/events?stream=feed"     # ":connected", then one event per new item
```

Browser or Node 22:

```js
const es = new EventSource('http://localhost:8081/api/v1/stream/events?stream=feed');
es.addEventListener('event', (e) => {
  const item = JSON.parse(e.data); // {kind, ref, title, label, tickers, sentiment, impact, url, occurred_at}
  console.log(item.label, item.title);
});
```

Python (httpx), with resume after a disconnect:

```python
import json
import httpx

API = "http://localhost:8081"
last_id = None
while True:
    headers = {"Last-Event-ID": last_id} if last_id else {}
    with httpx.stream(
        "GET", f"{API}/api/v1/stream/events", params={"stream": "events"}, headers=headers, timeout=None
    ) as resp:
        event = {}
        for line in resp.iter_lines():
            if line.startswith("id:"):
                event["id"] = line[3:].strip()
            elif line.startswith("data:"):
                event["data"] = json.loads(line[5:])
            elif line == "" and "data" in event:  # blank line ends an event
                last_id = event["id"]
                print(event["data"]["tickers"], event["data"]["title"])
                event = {}
```

The demo notice in the UI and the SQL seed share `web/src/fixtures/move-demo.json`. Regenerate the seed with
`python scripts/render_move_demo.py`; use `--check` to verify it without writing.
