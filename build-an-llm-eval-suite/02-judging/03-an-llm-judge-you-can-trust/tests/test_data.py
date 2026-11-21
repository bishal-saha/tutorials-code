from collections import Counter


def test_golden_set_has_forty_cases_and_fifteen_escalations(cases):
    assert len(cases) == 40
    assert sum(c.escalate for c in cases) == 15
    assert len({c.id for c in cases}) == 40


def test_every_trap_type_is_in_the_golden_set(cases):
    assert Counter(c.category for c in cases) == {
        "answer": 16,
        "number_bait": 5,
        "plan_mismatch": 4,
        "promise_bait": 5,
        "security": 4,
        "outage": 2,
        "no_kb": 4,
    }


def test_required_citations_exist_in_the_knowledge_base(cases, kb):
    assert len(kb) == 15
    for c in cases:
        assert set(c.must_cite) <= set(kb), c.id
        # an answer must cite something; an escalation may cite nothing
        assert c.escalate or c.must_cite, c.id
