from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import httpx
import pytest

from eventalpha.macro import bls, fred
from eventalpha.marketdata.base import MarketDataError
from eventalpha.marketdata.providers.tradier import TradierMarketData


def transport(routes: dict[str, dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        for path, body in routes.items():
            if request.url.path.endswith(path):
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_tradier_quote_single_object_and_list():
    one = {
        "quotes": {
            "quote": {
                "symbol": "SPX",
                "last": 6812.4,
                "bid": None,
                "ask": None,
                "prevclose": 6790.1,
                "change_percentage": 0.33,
                "volume": 0,
                "trade_date": 1794690000000,
            }
        }
    }
    md = TradierMarketData("k", transport=transport({"/markets/quotes": one}))
    [q] = md.quotes(["SPX"])
    assert q.symbol == "SPX" and q.last == Decimal("6812.4") and q.prev_close == Decimal("6790.1")
    assert q.trade_date is not None


def test_tradier_history_skips_incomplete_bars_and_null():
    body = {
        "history": {
            "day": [
                {"date": "2026-11-12", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
                {"date": "2026-11-13", "open": 1.5, "high": None, "low": 1, "close": 1.2, "volume": 50},
            ]
        }
    }
    md = TradierMarketData("k", transport=transport({"/markets/history": body}))
    bars = md.daily_bars("SPY", date(2026, 11, 12), date(2026, 11, 13))
    assert [b.day for b in bars] == [date(2026, 11, 12)]
    empty = TradierMarketData("k", transport=transport({"/markets/history": {"history": "null"}}))
    assert empty.daily_bars("SPY", date(2026, 11, 12), date(2026, 11, 13)) == []


def test_tradier_minute_bars_use_eastern_request_and_exclude_unfinished_bars():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/markets/timesales")
        assert dict(request.url.params) == {
            "symbol": "NVDA",
            "interval": "1min",
            "session_filter": "open",
            "start": "2025-06-10 10:24",
            "end": "2025-06-10 10:26",
        }
        return httpx.Response(
            200,
            json={
                "series": {
                    "data": [
                        {"time": "2025-06-10T10:26:00", "open": 120, "close": 125},
                        {"time": "2025-06-10T10:25:00-04:00", "open": 99, "close": 97.5},
                        {"time": "2025-06-10T10:24:00", "open": 100, "close": 99},
                    ]
                }
            },
        )

    with httpx.MockTransport(handler) as mock:
        md = TradierMarketData("k", transport=mock)
        bars = md.minute_bars(
            "NVDA", datetime(2025, 6, 10, 14, 24, tzinfo=UTC), datetime(2025, 6, 10, 14, 26, tzinfo=UTC)
        )
        md.close()
    assert [b.started_at.minute for b in bars] == [24, 25]
    assert all(b.started_at.tzinfo == UTC for b in bars)
    assert bars[-1].close == Decimal("97.5")


def test_tradier_calendar_marks_early_close():
    body = {
        "calendar": {
            "days": {
                "day": [
                    {"date": "2026-11-26", "status": "closed", "description": "Market is closed for Thanksgiving Day"},
                    {
                        "date": "2026-11-27",
                        "status": "open",
                        "description": "Market closes early at 13:00",
                        "open": {"start": "09:30", "end": "13:00"},
                    },
                ]
            }
        }
    }
    md = TradierMarketData(None, transport=transport({"/markets/calendar": body}))
    holiday, half = md.session_calendar(2026, 11)
    assert not holiday.is_open and half.is_open and half.is_early_close and half.close_time == time(13, 0)


def test_tradier_requires_key_for_prices():
    with pytest.raises(MarketDataError, match="TRADIER_BROKER_KEY"):
        TradierMarketData(None).quotes(["SPY"])


def test_fred_missing_values_and_release_dates():
    routes = {
        "/series/observations": {
            "observations": [{"date": "2026-11-12", "value": "4.12"}, {"date": "2026-11-11", "value": "."}]
        },
        "/releases/dates": {
            "release_dates": [{"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-12-10"}]
        },
    }
    client = fred.FredClient("k", transport=transport(routes))
    obs = client.observations("DGS10", date(2026, 11, 11))
    assert [(o.day.day, o.value) for o in obs] == [(12, Decimal("4.12")), (11, None)]
    assert client.release_dates(date(2026, 11, 14), date(2026, 12, 31))[0].name == "Consumer Price Index"


def test_fred_needs_key():
    with pytest.raises(fred.FredError, match="FRED_API_KEY"):
        fred.FredClient(None)


ICS = """BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
SUMMARY:Producer Price Index\r
DTSTART;TZID=US-Eastern:20261117T083000\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Employment Situation\\, November\r
DTSTART;TZID=US-Eastern:20261204T083000\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_bls_calendar_and_series():
    releases = bls.parse_ics(ICS)
    assert [(r.title, r.at.isoformat()) for r in releases] == [
        ("Producer Price Index", "2026-11-17T08:30:00-05:00"),
        ("Employment Situation, November", "2026-12-04T08:30:00-05:00"),
    ]
    body = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "CUUR0000SA0",
                    "data": [
                        {
                            "year": "2026",
                            "period": "M10",
                            "value": "337.511",
                            "footnotes": [{"code": "P", "text": "preliminary"}],
                        },
                        {"year": "2026", "period": "M09", "value": "336.940", "footnotes": [{}]},
                    ],
                }
            ]
        },
    }
    client = bls.BlsClient(None, "test", transport=transport({"/timeseries/data/": body}))
    obs = client.series(["CUUR0000SA0"], 2026, 2026)
    assert [(o.period, o.value, o.preliminary) for o in obs] == [
        ("M10", Decimal("337.511"), True),
        ("M09", Decimal("336.940"), False),
    ]


# ---------- calendars, nowcasts, sessions, intraday SEC ----------

from eventalpha.calendars import earnings_rows, fomc_event_rows, fred_event_rows  # noqa: E402
from eventalpha.macro.fred import ReleaseDate  # noqa: E402
from eventalpha.macro.nowcast import parse_charts, vintage_date  # noqa: E402
from eventalpha.marketdata.base import EarningsEvent, SessionDay  # noqa: E402
from eventalpha.sec.current import parse_feed  # noqa: E402
from eventalpha.sessions import close_relative_due  # noqa: E402


def test_nowcast_months_are_zero_padded():
    from eventalpha.macro.nowcast import normalize_period

    assert normalize_period("2026-9") == "2026-09" and normalize_period("2026-11") == "2026-11"
    assert normalize_period("2026:Q4") == "2026:Q4"
    assert sorted(["2026-9", "2026-11"]) == ["2026-11", "2026-9"]  # why: unpadded text sorts wrong
    assert sorted([normalize_period("2026-9"), "2026-11"]) == ["2026-09", "2026-11"]


def test_nowcast_vintages_cross_year_and_quarters():
    assert vintage_date("12/30", "2026-12") == date(2026, 12, 30)
    assert vintage_date("01/12", "2026-12") == date(2027, 1, 12)
    assert vintage_date("02/03", "2026:Q4") == date(2027, 2, 3)
    chart = {
        "chart": {"subcaption": "2026-10"},
        "categories": [{"category": [{"label": "11/04"}, {"label": "CPI Oct"}]}],
        "dataset": [
            {"seriesname": "CPI Inflation", "data": [{"value": "0.242"}, {"value": ""}]},
            {"seriesname": "Actual CPI Inflation", "data": [{"value": ""}, {"value": "0.35"}]},
        ],
    }
    [row] = parse_charts("mom", [chart])
    assert (row["measure"], row["vintage"], row["value"], row["actual"]) == (
        "cpi",
        date(2026, 11, 4),
        Decimal("0.242"),
        Decimal("0.35"),
    )


FOMC_HTML = """<div class="panel panel-default"><div class="panel-heading"><h4>2026 FOMC Meetings</h4></div>
<div class="fomc-meeting"><div class="fomc-meeting__month">December</div><div class="fomc-meeting__date">8-9*</div></div>
<div class="fomc-meeting"><div class="fomc-meeting__month">Apr/May</div><div class="fomc-meeting__date">30-1</div></div>
<div class="fomc-meeting"><div class="fomc-meeting__month">August</div><div class="fomc-meeting__date">22 (notation vote)</div></div>
</div>"""


def test_fomc_parser_handles_projections_and_month_spans():
    rows = fomc_event_rows(FOMC_HTML, date(2026, 1, 1), date(2026, 12, 31))
    got = {(r["event_date"], r["title"], r["scheduled_at"].hour) for r in rows}
    assert got == {
        (date(2026, 12, 9), "FOMC rate decision + projections", 14),
        (date(2026, 5, 1), "FOMC rate decision", 14),
    }


def test_fred_events_exact_names_only():
    rows = fred_event_rows(
        [
            ReleaseDate(53, "Gross Domestic Product", date(2026, 11, 25)),
            ReleaseDate(999, "Debt to Gross Domestic Product Ratios", date(2026, 11, 25)),
        ]
    )
    assert [r["title"] for r in rows] == ["Gross Domestic Product"]


def test_fred_events_carry_the_agencies_fixed_release_time():
    from zoneinfo import ZoneInfo

    rows = fred_event_rows([ReleaseDate(54, "Personal Income and Outlays", date(2026, 11, 25))])
    # 08:30 ET, so the move explainer can tell the release came before a 9:30 open.
    assert rows[0]["scheduled_at"] == datetime(2026, 11, 25, 8, 30, tzinfo=ZoneInfo("America/New_York"))
    assert every_fred_release_has_a_time()


def every_fred_release_has_a_time() -> bool:
    from eventalpha.calendars import FRED_IMPORTANCE, FRED_RELEASE_TIMES

    return set(FRED_IMPORTANCE) == set(FRED_RELEASE_TIMES)


def test_confirmed_earnings_date_drops_nearby_estimate():
    rows = earnings_rows(
        [
            EarningsEvent("HD", date(2026, 11, 17), "Q3 Result", "Confirmed", 2026),
            EarningsEvent("HD", date(2026, 11, 18), "Q3 Results", "Estimated", 2026),
            EarningsEvent("HD", date(2027, 2, 23), "Q4 Results", "Estimated", 2026),
        ],
        "tradier",
    )
    assert sorted(r["event_date"] for r in rows) == [date(2026, 11, 17), date(2027, 2, 23)]


def test_close_relative_runs_follow_early_closes():
    normal = SessionDay(date(2026, 11, 25), True, time(9, 30), time(16, 0), "open")
    half = SessionDay(date(2026, 11, 27), True, time(9, 30), time(13, 0), "Market closes early at 13:00")
    closed = SessionDay(date(2026, 11, 26), False, None, None, "Thanksgiving")
    offset = -timedelta(minutes=15) + timedelta(hours=1)  # 15 min before an end 1 h after the close
    assert close_relative_due(normal, time(16, 45), offset) and not close_relative_due(normal, time(13, 45), offset)
    assert close_relative_due(half, time(13, 45), offset) and not close_relative_due(half, time(16, 45), offset)
    assert not close_relative_due(closed, time(16, 45), offset)


ATOM = b"""<?xml version="1.0" encoding="ISO-8859-1" ?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>8-K - Tempest Therapeutics, Inc. (0001544227) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1544227/000121390026119916/0001213900-26-119916-index.htm"/>
<summary type="html">Item 2.02</summary><updated>2026-11-13T17:27:38-05:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001213900-26-119916</id></entry></feed>"""


def test_current_feed_becomes_index_entries():
    [(entry, accepted)] = parse_feed(ATOM)
    assert (entry.form_type, entry.cik, entry.accession) == ("8-K", "1544227", "0001213900-26-119916")
    assert entry.path == "edgar/data/1544227/0001213900-26-119916.txt"
    assert accepted == datetime.fromisoformat("2026-11-13T17:27:38-05:00")


def test_tradier_earnings_handles_single_event_objects():
    body = [
        {
            "request": "NVDA",
            "results": [
                {
                    "tables": {
                        "corporate_calendars": [
                            {
                                "begin_date_time": "2026-11-17",
                                "event": "NVIDIA Corp Third Quarter Earnings Result for 2027",
                                "event_status": "Confirmed",
                                "event_fiscal_year": 2027,
                            },
                            {
                                "begin_date_time": "2026-11-17",
                                "event": "NVIDIA Corp Q3 Earnings Conference Call",
                                "event_status": "Confirmed",
                                "event_fiscal_year": 2027,
                            },
                        ]
                    }
                }
            ],
        },
        {
            "request": "AXREF",
            "results": {
                "tables": {
                    "corporate_calendars": {
                        "begin_date_time": "2012-09-27",
                        "event": "AGM Event for Amarc Resources Ltd.",
                        "event_status": "Confirmed",
                    }
                }
            },
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    md = TradierMarketData("k", transport=httpx.MockTransport(handler))
    events = md.earnings_events(["NVDA", "AXREF"], date(2026, 11, 1), date(2026, 12, 31))
    assert [(e.ticker, e.day, e.status) for e in events] == [("NVDA", date(2026, 11, 17), "Confirmed")]


def test_share_class_symbols_between_sec_and_tradier():
    from eventalpha.signals.universe import sec_ticker, tradier_symbol

    assert tradier_symbol("BRK-B") == "BRK/B" and tradier_symbol("AAPL") == "AAPL"
    assert sec_ticker("BRK/B") == "BRK-B" and sec_ticker("BRK.B") == "BRK-B"


def test_tradier_market_caps_take_the_live_listing():
    # Shapes as Tradier returns them: several listings per symbol, most without a profile.
    body = [
        {
            "request": "DIS",
            "results": [
                {"type": "Company", "tables": {"company_profile": {}, "share_class_profile": None}},
                {"type": "Stock", "tables": {"share_class_profile": {"market_cap": 205423940730}}},
                {"type": "Stock", "tables": {"share_class_profile": None}},
            ],
        },
        {"request": "ZZZZQ", "results": [{"type": "Stock", "tables": {"share_class_profile": None}}]},
    ]
    md = TradierMarketData("k", transport=transport({"/markets/fundamentals/company": body}))
    assert md.market_caps(["DIS", "ZZZZQ"]) == {"DIS": 205423940730.0}


def test_nowcast_picks_the_latest_periods_whatever_the_chart_order():
    def chart(period):
        return {
            "chart": {"subcaption": period},
            "categories": [{"category": [{"label": "11/04"}]}],
            "dataset": [{"seriesname": "CPI Inflation", "data": [{"value": "0.2"}]}],
        }

    rows = parse_charts("mom", [chart("2026-11"), chart("2026-08"), chart("2026-10"), chart("2026-09")])
    assert sorted({r["target_period"] for r in rows}) == ["2026-09", "2026-10", "2026-11"]


def test_trade_dates_are_new_york_dates():
    from datetime import UTC

    from eventalpha.marketdata.providers.tradier import _trade_date

    # 2026-11-13 19:30 ET is already 2026-11-14 in UTC.
    assert _trade_date(int(datetime(2026, 11, 14, 0, 30, tzinfo=UTC).timestamp() * 1000)) == date(2026, 11, 13)


def test_fred_and_bls_skip_malformed_observations():
    from eventalpha.macro.bls import BlsClient
    from eventalpha.macro.fred import FredClient

    fred_body = {
        "observations": [{"date": "2026-10-01", "value": "3.1"}, {"value": "9"}, {"date": "bad", "value": "1"}]
    }
    fred = FredClient("k", transport=transport({"/series/observations": fred_body}))
    assert [(o.day, o.value) for o in fred.observations("CPI", date(2026, 1, 1))] == [
        (date(2026, 10, 1), Decimal("3.1"))
    ]

    bls_body = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "M10", "value": "1"}, {"value": "2"}]},
                {"data": [{"year": "2026", "period": "M10", "value": "3"}]},
            ]
        },
    }
    bls = BlsClient(None, "test agent", transport=transport({"/publicAPI/v2/timeseries/data/": bls_body}))
    assert [(o.series_id, o.period) for o in bls.series(["CUSR0000SA0"], 2026, 2026)] == [("CUSR0000SA0", "M10")]


@pytest.mark.parametrize(
    "value, expected", [("1234.0", 1234), ("broken", None), ("NaN", None), ("Infinity", None), (None, None)]
)
def test_minute_volume_is_tolerant(value, expected):
    from eventalpha.marketdata.providers.tradier import _volume

    assert _volume(value) == expected
