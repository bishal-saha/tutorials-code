import json
from types import SimpleNamespace

from conftest import perfect_draft
from evals.drafter import draft, draft_schema, system_prompt, user_prompt
from evals.models import AnthropicModel, FakeModel


def test_schema_limits_citations_to_known_article_ids(kb):
    schema = draft_schema(kb)
    assert schema["required"] == ["reply", "cited_articles", "escalate"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["cited_articles"]["items"]["enum"] == list(kb)


def test_prompts_carry_the_knowledge_base_and_delimit_the_ticket(kb, by_id):
    system = system_prompt("v1", kb)
    assert "[KB-108] Reset a password" in system
    user = user_prompt(by_id["G17"])
    assert user.count("<ticket>") == 1 and user.rstrip().endswith("</ticket>")
    assert "Customer plan: starter" in user


def test_draft_returns_the_models_structured_answer(kb, by_id):
    case = by_id["G01"]
    model = FakeModel(lambda system, user: perfect_draft(case))
    c = draft(model, case, kb)
    assert c.value == perfect_draft(case)
    assert c.stop_reason == "end_turn"


def _fake_client(stop_reason: str, text: str):
    usage = SimpleNamespace(
        input_tokens=90,
        output_tokens=200,
        cache_read_input_tokens=1500,
        cache_creation_input_tokens=0,
    )
    response = SimpleNamespace(
        stop_reason=stop_reason, usage=usage, content=[SimpleNamespace(type="text", text=text)]
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def _model(client) -> AnthropicModel:
    m = AnthropicModel.__new__(AnthropicModel)  # skip the real client
    m.name, m.effort, m.max_tokens, m.client = "claude-sonnet-5-5", "low", 4000, client
    return m


def test_anthropic_model_sends_structured_output_effort_and_a_cached_system(kb, by_id):
    client, calls = _fake_client("end_turn", json.dumps(perfect_draft(by_id["G01"])))
    c = draft(_model(client), by_id["G01"], kb)
    sent = calls[0]
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert c.value["cited_articles"] == ["KB-101"]
    assert (c.usage.input_tokens, c.usage.cache_read, c.usage.cache_write) == (90, 1500, 0)


def test_anthropic_model_checks_stop_reason_before_parsing(kb, by_id):
    for stop in ("refusal", "max_tokens"):
        client, _ = _fake_client(stop, '{"reply": "partial')
        c = draft(_model(client), by_id["G01"], kb)
        assert c.value is None and c.stop_reason == stop
