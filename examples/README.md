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
DELETE FROM articles WHERE source_id LIKE 'demo-%';
DELETE FROM insider_transactions WHERE accession LIKE 'demo-%';
DELETE FROM econ_events WHERE event_key LIKE 'demo-%';
DELETE FROM earnings_events WHERE source = 'demo';
DELETE FROM signals WHERE message LIKE '%(demo)%';
DELETE FROM ticker_universe WHERE ticker IN ('DEMOA', 'DEMOB', 'DEMOC');
COMMIT;
```

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
