"""Telegram (HTML) rendering of a signal. Short enough to read on a phone in 30 seconds."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from eventalpha.signals.build import Signal

NY = ZoneInfo("America/New_York")


def _e(s: Any) -> str:
    return html.escape(str(s))


def _dir(score: float | None) -> str:
    if score is None:
        return "⚪ no read (no scored news)"
    label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[label]
    return f"{icon} {label} {score:+.2f}"


def _moves(moves: list[dict[str, Any]], symbols: tuple[str, ...]) -> str:
    parts = [
        f"{m['symbol']} {m['change_pct']:+.2f}%"
        for m in moves
        if m["symbol"] in symbols and m.get("change_pct") is not None
    ]
    return " · ".join(parts) or "n/a"


def _freshness(signal: Signal) -> str:
    def t(key: str) -> str:
        v = signal.inputs_as_of.get(key)
        if not v:
            return "never"
        try:
            return datetime.fromisoformat(v).astimezone(NY).strftime("%m-%d %H:%M")
        except ValueError:
            return v

    return (
        f"<i>data: filings {t('sec_filing_processed')} · news {t('articles_ingested')} · "
        f"scores {t('articles_scored')} · prices {t('market_snapshot')} ET</i>"
    )


def render_spx_overnight(s: Signal) -> str:
    p = s.payload
    lines = [
        f"<b>SPX overnight · {s.session_date:%a %b %d}</b>",
        f"{_dir(s.score)} · confidence {s.confidence or 0:.0%}",
        f"close: {_moves(p['market_close'], ('SPX', 'VIX', 'TLT', 'USO', 'UUP', 'HYG'))}",
    ]
    c = p["counts"]
    lines.append(
        f"news: {c['company_specific']} company items ({c['megacap_articles']} top-100)"
        + (f", <b>{c['unscored']} not yet scored</b>" if c["unscored"] else "")
    )
    for a in p["megacap_news"][:5]:
        lines.append(
            f"• {_e(a['company'])} ({a['cap_weight']:.1f}% wt): {_e(a['sentiment'])} "
            f"{a['sentiment_score']:+.2f}, mat {a['materiality']:.1f}: {_e(a['title'][:90])}"
        )
    if p["earnings_today"]:
        lines.append("reported today: " + ", ".join(e["ticker"] for e in p["earnings_today"]))
    if p["earnings_next_session"]:
        lines.append("report next session: " + ", ".join(e["ticker"] for e in p["earnings_next_session"]))
    if p["macro_next_session"]:
        flag = "⚠️ " if p["macro_risk_next_session"] else ""
        lines.append(
            flag
            + "next session: "
            + " · ".join(f"{m['time'] or 'date only'} {_e(m['title'])}" for m in p["macro_next_session"])
        )
    lines.append(_freshness(s))
    lines.append("<i>Research signal, not advice.</i>")
    return "\n".join(lines)


def render_premarket(s: Signal) -> str:
    p = s.payload
    lines = [
        f"<b>Premarket · {s.session_date:%a %b %d}</b>",
        f"news tone {_dir(s.score)} · {p['counts']['companies']} companies with material news"
        + (f", <b>{p['counts']['unscored']} not yet scored</b>" if p["counts"]["unscored"] else ""),
        f"premarket: {_moves(p['premarket_moves'], ('SPY', 'QQQ', 'IWM', 'TLT', 'USO', 'UUP'))}",
    ]
    for c in p["cpi_surprise"]:
        lines.append(
            f"📊 {c['measure'].upper()} {c['period']}: {c['actual_mom']:+.2f}% m/m vs nowcast "
            f"{c['nowcast_mom']:+.2f}% (surprise {c['surprise']:+.2f})"
        )
    if p["macro_today"]:
        lines.append("today: " + " · ".join(f"{m['time'] or 'date only'} {_e(m['title'])}" for m in p["macro_today"]))
    for a in p["tickers"][:10]:
        ev = f" [{', '.join(a['events'][:2])}]" if a["events"] else ""
        lines.append(
            f"• <b>{_e('/'.join(a['tickers'][:2]))}</b> {_e(a['sentiment'])} {a['sentiment_score']:+.2f}, "
            f"mat {a['materiality']:.1f}{_e(ev)}: {_e(a['title'][:80])}"
        )
    if p["insider_buys"]:
        lines.append(
            "insider buys: "
            + "; ".join(
                f"{_e(b['ticker'])} {_e(b['owner_name'])} ${b['value'] / 1e6:.1f}M ({b['insiders_30d']} in 30d)"
                for b in p["insider_buys"][:5]
            )
        )
    if p["earnings_today"]:
        lines.append("earnings today: " + ", ".join(e["ticker"] for e in p["earnings_today"][:20]))
    lines.append(_freshness(s))
    lines.append("<i>Research signal, not advice.</i>")
    return "\n".join(lines)
