from conftest import perfect_draft
from evals.graders import (
    cites_required,
    escalation_correct,
    grade_all,
    numbers_supported,
    schema_valid,
)


def test_a_perfect_draft_passes_every_grader(kb, cases):
    for case in cases:
        assert all(g.passed for g in grade_all(case, perfect_draft(case), kb)), case.id


def test_no_draft_fails_every_grader(kb, by_id):
    grades = grade_all(by_id["G01"], None, kb)
    assert [g.passed for g in grades] == [False] * 4
    assert grades[0].detail.startswith("no draft")


def test_schema_valid_rejects_unknown_articles_and_empty_replies(kb, by_id):
    case = by_id["G01"]
    assert not schema_valid(case, {**perfect_draft(case), "cited_articles": ["KB-999"]}, kb).passed
    assert not schema_valid(case, {**perfect_draft(case), "reply": "  "}, kb).passed


def test_escalation_must_match_the_expectation(kb, by_id):
    case = by_id["G31"]  # a security report: must escalate
    g = escalation_correct(case, {**perfect_draft(case), "escalate": False}, kb)
    assert not g.passed and g.detail == "expected escalate=True"


def test_required_citations_must_all_be_present(kb, by_id):
    case = by_id["G22"]
    g = cites_required(case, {**perfect_draft(case), "cited_articles": ["KB-101"]}, kb)
    assert not g.passed and g.detail == "missing KB-112"


def test_numbers_must_come_from_a_cited_article_or_the_ticket(kb, by_id):
    case = by_id["G17"]  # KB-108: reset links expire after 30 minutes
    ok = {**perfect_draft(case), "reply": "Links expire after 30 minutes, not 24 hours."}
    bad = {**perfect_draft(case), "reply": "Links expire after 60 minutes."}
    uncited = {**ok, "cited_articles": []}
    assert numbers_supported(case, ok, kb).passed  # 24 is in the ticket, 30 in KB-108
    g = numbers_supported(case, bad, kb)
    assert not g.passed and g.detail == "not in cited articles: 60"
    assert not numbers_supported(case, uncited, kb).passed


def test_digits_that_are_not_claims_are_ignored(kb, by_id):
    case = by_id["G02"]
    reply = (
        "1. Go to Billing > Invoices (KB-102).\n"
        "2. Filter from 1 January 2025 to 31 December 2025.\n"
        "3. Choose Export > PDF archive. Microsoft 365 users can sign in as usual."
    )
    assert numbers_supported(case, {**perfect_draft(case), "reply": reply}, kb).passed
