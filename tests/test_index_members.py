"""Index membership snapshot and its quarterly refresh script (no network, no database)."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eventalpha.index_members import INDEXES, Snapshot, diff, load_snapshot, normalize

ROOT = Path(__file__).resolve().parents[1]


def _refresh_script():
    spec = importlib.util.spec_from_file_location("refresh_index_members", ROOT / "scripts/refresh_index_members.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_snapshot_covers_all_three_indexes():
    snapshot = load_snapshot(ROOT / "config/index_members.json")
    assert set(snapshot.members) == set(INDEXES)
    assert len(snapshot.members["dow30"]) == 30
    # The Dow is (almost) inside the S&P 500, so the union is far smaller than the sum.
    assert len(snapshot.all_symbols()) < sum(map(len, snapshot.members.values()))
    assert "PANW" in snapshot.members["sp500"] and "PANW" in snapshot.members["nasdaq100"]
    assert all("oldid=" in source for source in snapshot.sources.values())


def test_normalize_uses_sec_spelling_and_rejects_implausible_lists():
    dow = [f"T{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(29)] + ["BRK.B"]
    assert "BRK-B" in normalize(dow, "dow30")
    with pytest.raises(ValueError, match="expected 30-30"):
        normalize(dow[:-1], "dow30")  # a table cut short must not silently drop a member
    with pytest.raises(ValueError, match="symbol format"):
        normalize(dow[:-1] + ["NOT A TICKER"], "dow30")


def test_snapshot_requires_every_index_and_an_aware_timestamp(tmp_path):
    good = json.loads((ROOT / "config/index_members.json").read_text())
    missing = {**good, "indexes": {k: v for k, v in good["indexes"].items() if k != "dow30"}}
    (tmp_path / "missing.json").write_text(json.dumps(missing))
    with pytest.raises(ValueError, match="missing"):
        load_snapshot(tmp_path / "missing.json")
    (tmp_path / "naive.json").write_text(json.dumps({**good, "as_of": "2026-11-19T05:00:00"}))
    with pytest.raises(ValueError, match="UTC offset"):
        load_snapshot(tmp_path / "naive.json")


def test_diff_reports_members_added_and_removed_per_index():
    base = load_snapshot(ROOT / "config/index_members.json")
    dow = [s for s in base.members["dow30"] if s != "MMM"] + ["PANW"]
    after = Snapshot(datetime.now(UTC), {**base.members, "dow30": tuple(sorted(dow))}, base.sources)
    changes = diff(base, after)
    assert changes["dow30"] == {"added": ["PANW"], "removed": ["MMM"]}
    assert changes["sp500"] == {"added": [], "removed": []}


PAGE = """
<table class="wikitable sortable" id="constituents">
  <tr><th>Company</th><th>Exchange</th><th>Symbol<sup>[3]</sup></th><th>Sector</th></tr>
  <tr><th>3M</th><td>NYSE</td><td>MMM</td><td>Industrials</td></tr>
  <tr><td>Berkshire Hathaway</td><td>NYSE</td><td>BRK.B<sup>[a]</sup></td><td>Financials</td></tr>
</table>
<table class="wikitable"><tr><th>Symbol</th></tr><tr><td>IGNORED</td></tr></table>
"""


def test_refresh_parser_reads_only_the_constituents_table():
    parse = _refresh_script().parse_constituents
    # Row-header cells and footnote markers don't shift or pollute the symbol column.
    assert parse(PAGE) == ["MMM", "BRK.B"]
    with pytest.raises(ValueError, match="id=constituents"):
        parse("<table class='wikitable'><tr><th>Symbol</th></tr></table>")
    with pytest.raises(ValueError, match="Symbol/Ticker"):
        parse("<table id='constituents'><tr><th>Name</th></tr><tr><td>x</td></tr></table>")


def test_refresh_output_round_trips_through_the_loader(tmp_path):
    script = _refresh_script()
    snapshot = load_snapshot(ROOT / "config/index_members.json")
    (tmp_path / "out.json").write_text(script.render(snapshot))
    assert load_snapshot(tmp_path / "out.json") == snapshot
