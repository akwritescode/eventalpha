"""Filing families: which forms each daily SEC DAG collects, and how one batch is processed.

Every processed filing gets a row in the `sec_filings` ledger (loaded / skipped / failed),
so coverage per day is queryable and failures can be found and re-run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine

from eventalpha import db
from eventalpha.sec import events, form4, form13f, periodic
from eventalpha.sec.client import RateLimitedClient
from eventalpha.sec.index import IndexEntry
from eventalpha.sec.registry import Family
from eventalpha.sec.submission import fetch_submission

log = logging.getLogger(__name__)

CikMap = dict[str, tuple[str, list[str]]]


@dataclass
class Outcome:
    status: str  # loaded | skipped | failed
    rows: int = 0
    detail: str | None = None


def _events(client: RateLimitedClient, engine: Engine, entries: Sequence[IndexEntry], cik_map: CikMap):
    articles, outcomes = [], {}
    for e in entries:
        article = events.to_article(e, fetch_submission(client, e), cik_map)
        if article is None:
            outcomes[e.accession] = Outcome("skipped", detail="issuer not in universe")
        else:
            articles.append(article)
            outcomes[e.accession] = Outcome("loaded", 1)
    return outcomes, lambda: db.upsert_articles(engine, articles)


def _insider(client: RateLimitedClient, engine: Engine, entries: Sequence[IndexEntry], cik_map: CikMap):
    rows, outcomes = [], {}
    for e in entries:
        parsed = form4.parse_form4(e, fetch_submission(client, e))
        if not parsed or parsed[0]["issuer_cik"] not in cik_map:
            outcomes[e.accession] = Outcome("skipped", detail="no transactions or issuer not listed")
            continue
        for r in parsed:  # issuer's own ticker list beats the free-text symbol field
            r["ticker"] = (cik_map[r["issuer_cik"]][1] or [r["ticker"]])[0]
        rows.extend(parsed)
        outcomes[e.accession] = Outcome("loaded", len(parsed))
    loaded = [a for a, o in outcomes.items() if o.status == "loaded"]
    return outcomes, lambda: db.replace_by_accession(engine, "insider_transactions", loaded, rows)


def _holdings(client: RateLimitedClient, engine: Engine, entries: Sequence[IndexEntry], cik_map: CikMap):
    headers, rows, outcomes = [], [], {}
    for e in entries:
        header, holdings = form13f.parse_13f(e, fetch_submission(client, e))
        headers.append(header)
        rows.extend(holdings)
        outcomes[e.accession] = Outcome("loaded", len(holdings))

    def load():
        db.upsert_rows(engine, "institutional_filings", headers, key=["accession"])
        return db.replace_by_accession(engine, "institutional_holdings", [h["accession"] for h in headers], rows)

    return outcomes, load


def _periodic(client: RateLimitedClient, engine: Engine, entries: Sequence[IndexEntry], cik_map: CikMap):
    sections, facts, outcomes = [], [], {}
    for e in entries:
        s = periodic.section_rows(e, fetch_submission(client, e))
        f = periodic.fetch_fact_rows(client, e)
        sections.extend(s)
        facts.extend(f)
        outcomes[e.accession] = Outcome("loaded", len(s) + len(f), detail=f"{len(s)} sections, {len(f)} facts")
    accessions = list(outcomes)

    def load():
        db.replace_by_accession(engine, "report_sections", accessions, sections)
        return db.replace_by_accession(engine, "financial_facts", accessions, facts)

    return outcomes, load


PROCESSORS: dict[str, Callable] = {
    "events": _events,
    "insider": _insider,
    "holdings": _holdings,
    "periodic": _periodic,
}


def process_batch(
    family: Family, client: RateLimitedClient, engine: Engine, entries: Sequence[IndexEntry], cik_map: CikMap
) -> dict[str, Any]:
    """Fetch, parse and load one batch. A filing that fails is recorded and skipped; the
    batch raises (and Airflow retries it) only when most of it fails."""
    outcomes: dict[str, Outcome] = {}
    good: list[IndexEntry] = []
    for e in entries:  # isolate per-filing failures before the batch load
        try:
            o, load = PROCESSORS[family.name](client, engine, [e], cik_map)
            outcomes.update(o)
            good.append(e)
            load()
        except Exception as exc:
            log.warning("failed %s %s: %r", e.form_type, e.accession, exc)
            outcomes[e.accession] = Outcome("failed", detail=repr(exc)[:500])
    db.record_filings(engine, family.name, entries, outcomes)
    failed = sum(o.status == "failed" for o in outcomes.values())
    if failed > len(entries) // 2:
        raise RuntimeError(f"{failed}/{len(entries)} {family.name} filings failed")
    return {
        status: sum(o.status == status for o in outcomes.values()) for status in ("loaded", "skipped", "failed")
    } | {"rows": sum(o.rows for o in outcomes.values())}
