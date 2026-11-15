"""Filing families and their forms, with no imports beyond the standard library.

DAG files import this at parse time, which runs every time a task starts; it has to stay
cheap. The parsers (events, form4, form13f, periodic) import their form sets from here.
"""

from __future__ import annotations

from dataclasses import dataclass

EVENT_FORMS = frozenset({"8-K", "6-K", "SCHEDULE 13D", "SCHEDULE 13D/A", "S-1", "424B4", "424B5"})
INSIDER_FORMS = frozenset({"4", "4/A"})
HOLDINGS_FORMS = frozenset({"13F-HR", "13F-HR/A"})
PERIODIC_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})


@dataclass(frozen=True)
class Family:
    name: str
    forms: frozenset[str]
    universe_only: bool  # keep only filings whose CIK is a listed company
    batch_size: int
    description: str
    # Airflow priority_weight inside the shared `sec_edgar` pool: when slots are scarce (a 13F
    # deadline day in earnings season), higher-priority families' batches start first.
    priority: int


FAMILIES: dict[str, Family] = {
    f.name: f
    for f in (
        Family("events", EVENT_FORMS, True, 25, "8-K, 6-K, Schedule 13D, S-1, 424B4/5 → articles (classified)", 40),
        Family("insider", INSIDER_FORMS, True, 100, "Form 4 insider transactions", 30),
        Family("holdings", HOLDINGS_FORMS, False, 40, "13F-HR institutional holdings", 10),
        Family("periodic", PERIODIC_FORMS, True, 10, "10-K / 10-Q sections and XBRL facts", 20),
    )
}
