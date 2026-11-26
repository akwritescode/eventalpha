"""Exercise the offline grader with known-good and adversarial API responses."""

import json

from scripts.eval_move_explanations import DEFAULT_CASES, grade

START = "2026-11-25T11:00:00-05:00"
END = "2026-11-25T14:00:00-05:00"
WINDOW = {"ticker": "SPY", "start": START, "end": END, "asOf": END}


def source(evidence_id, status="original_source", first_seen=START):
    return {
        "id": evidence_id,
        "publishedAt": START,
        "firstSeenAt": first_seen,
        "status": status,
        "url": "https://example.com/evidence",
    }


def test_expected_catalyst_is_retrieved_and_cited():
    case = {**WINDOW, "expected": "catalyst", "expectedEvidenceIds": ["article:1"]}
    result = {
        **WINDOW,
        "timeline": [source("article:1")],
        "candidateEvidenceIds": ["article:1"],
        "catalysts": [{"evidenceId": "article:1"}],
    }
    grades = grade(case, result)
    assert grades["candidate_recall"] == 1.0
    assert grades["citations_match_labels"]
    assert grades["citations_valid"]


def test_nvda_case_rejects_an_always_abstaining_system():
    cases = json.loads(DEFAULT_CASES.read_text())
    case = next(case for case in cases if case["id"] == "nvda-h20-export-controls")
    filing = {
        **source("article:923", first_seen="2025-04-15T17:26:00-04:00"),
        "publishedAt": "2025-04-15T17:22:59-04:00",
        "url": case["expectedEvidenceUrls"][0],
    }
    result = {**case, "timeline": [filing], "candidateEvidenceIds": [filing["id"]], "catalysts": []}
    grades = grade(case, result)
    assert grades["candidate_recall"] == 1.0
    assert not grades["decision_correct"]
    assert not grades["citations_match_labels"]
    result["catalysts"] = [{"evidenceId": filing["id"]}]
    grades = grade(case, result)
    assert grades["decision_correct"]
    assert grades["citations_match_labels"]
    assert grades["citations_valid"]


def test_a_recap_is_context_and_late_evidence_is_reported():
    case = {**WINDOW, "expected": "abstain", "requiredContextIds": ["release:1"]}
    result = {
        **WINDOW,
        "timeline": [
            source("article:1", "market_commentary"),
            source("release:1", "economic_release", "2026-11-25T14:01:00-05:00"),
        ],
        "candidateEvidenceIds": ["article:1"],
        "catalysts": [{"evidenceId": "article:1"}],
    }
    grades = grade(case, result)
    assert not grades["decision_correct"]
    assert not grades["citations_valid"]
    assert not grades["required_context_present"]
    assert grades["late_evidence_ids"] == ["release:1"]


def test_abstention_still_passes_with_eligible_calendar_context():
    case = {**WINDOW, "expected": "abstain", "requiredContextIds": ["release:1"]}
    result = {
        **WINDOW,
        "timeline": [source("release:1", "economic_release")],
        "candidateEvidenceIds": [],
        "catalysts": [],
    }
    grades = grade(case, result)
    assert grades["decision_correct"]
    assert grades["required_context_present"]
    assert grades["late_evidence_ids"] == []
