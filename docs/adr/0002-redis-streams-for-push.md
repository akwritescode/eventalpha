# 0002. Redis Streams carry events to the API, Telegram and browsers

* Status: Accepted
* Date: 2026-11-14

## Context

New high-impact events must reach a Telegram channel, and every new stream item must reach
open browser tabs without polling. Postgres `LISTEN/NOTIFY` was the simplest option, since the
warehouse is already Postgres.

## Decision

The pipeline appends to two Redis Streams after each database commit: `eventalpha:events`
(high-impact only, relayed to Telegram through a consumer group) and `eventalpha:feed` (every
new item, pushed to browsers over Server-Sent Events). A Lua script makes each publish
idempotent (`SET NX` mark plus `XADD` in one step).

## Consequences

* Consumers resume from the last ID they saw, so an API restart or an offline relay catches up
  instead of losing events (`NOTIFY` messages are gone if nobody is listening).
* Consumer groups give at-least-once delivery to Telegram with acknowledgements.
* Publishing only after the commit means a stream never announces data the API can't serve.
* One more stateful service to run (Redis with AOF persistence), and streams are capped
  (`MAXLEN`), so the warehouse stays the system of record.
