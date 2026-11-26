#!/usr/bin/env python3
"""Capture and score EventAlpha move explanations against point-in-time labels."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "move_explanations.json"
WINDOW_FIELDS = ("start", "end", "asOf")


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError(f"Timestamp requires a timezone: {value}")
    return result


def fetch(base_url: str, case: dict) -> dict:
    ticker = quote(case["ticker"], safe="")
    query = urlencode({field: case[field] for field in WINDOW_FIELDS})
    url = f"{base_url.rstrip('/')}/api/v1/tickers/{ticker}/move-explanation?{query}"
    with urlopen(url, timeout=90) as response:
        return json.load(response)["data"]


def grade(case: dict, result: dict) -> dict:
    cutoff = instant(case["asOf"])
    end = instant(case["end"])
    evidence = {item["id"]: item for item in result["timeline"]}
    candidates = result["candidateEvidenceIds"]
    cited = [item["evidenceId"] for item in result["catalysts"]]
    expected = set(case.get("expectedEvidenceIds", []))
    expected_citations = set(case.get("acceptedCitationIds", expected))
    expected_urls = set(case.get("expectedEvidenceUrls", []))
    citation_urls = set(case.get("acceptedCitationUrls", expected_urls))
    retrieved_urls = {evidence[item].get("url") for item in candidates if item in evidence}
    labeled_citations = expected_citations | {item for item, row in evidence.items() if row.get("url") in citation_urls}
    required_context = set(case.get("requiredContextIds", []))
    eligible_status = {"original_source", "explains_move"}
    late_evidence = {
        item["id"]
        for item in evidence.values()
        if any(
            item.get(field) and instant(item[field]) > cutoff for field in ("publishedAt", "firstSeenAt", "verifiedAt")
        )
    }
    eligible_ids = {
        item["id"]
        for item in evidence.values()
        if item["id"] not in late_evidence and instant(item["publishedAt"]) <= end
    }
    eligible_citations = {
        evidence_id
        for evidence_id in eligible_ids
        if evidence[evidence_id]["status"] in eligible_status and evidence[evidence_id].get("url")
    }
    abstains = case["expected"] == "abstain"
    late_prices = sorted(
        {
            price["symbol"]
            for price in result.get("priceMoves", [])
            if price.get("dataAsOf") and instant(price["dataAsOf"]) > cutoff
        }
    )
    return {
        "window_matches": result["ticker"] == case["ticker"]
        and all(instant(result[field]) == instant(case[field]) for field in WINDOW_FIELDS),
        "candidate_recall": (
            (len(expected.intersection(candidates)) + len(expected_urls.intersection(retrieved_urls)))
            / (len(expected) + len(expected_urls))
            if expected or expected_urls
            else None
        ),
        "shortlist_valid": len(set(candidates)) == len(candidates) and set(candidates) <= eligible_ids,
        "decision_correct": not cited if abstains else bool(cited),
        "citations_valid": set(cited) <= eligible_citations,
        "citations_match_labels": (not cited if abstains else bool(cited) and set(cited) <= labeled_citations),
        "required_context_present": required_context <= eligible_ids,
        "late_evidence_ids": sorted(late_evidence),
        "late_price_symbols": late_prices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base-url", help="EventAlpha API origin")
    source.add_argument("--responses", type=Path, help="Previously saved responses keyed by case ID")
    parser.add_argument("--save-responses", type=Path, help="Save the responses used in this run")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    if not cases or len({case["id"] for case in cases}) != len(cases):
        parser.error("The eval set must contain unique case IDs and at least one case.")
    for case in cases:
        expected = case["expected"]
        if expected not in {"abstain", "catalyst"}:
            parser.error(f"Unknown expected decision for {case['id']}: {expected}")
        if expected == "catalyst" and not any(
            case.get(field)
            for field in ("acceptedCitationIds", "expectedEvidenceIds", "acceptedCitationUrls", "expectedEvidenceUrls")
        ):
            parser.error(f"Catalyst case {case['id']} needs at least one accepted citation ID or URL.")
    responses = (
        json.loads(args.responses.read_text())
        if args.responses
        else {case["id"]: fetch(args.base_url, case) for case in cases}
    )
    if args.save_responses:
        args.save_responses.write_text(json.dumps(responses, indent=2) + "\n")
    report = {case["id"]: grade(case, responses[case["id"]]) for case in cases}
    failed = [
        case_id
        for case_id, metrics in report.items()
        if any(value is False for value in metrics.values())
        or metrics["late_evidence_ids"]
        or metrics["late_price_symbols"]
        or metrics["candidate_recall"] not in (None, 1.0)
    ]
    print(json.dumps({"cases": report, "passed": len(report) - len(failed), "failed": failed}, indent=2))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
