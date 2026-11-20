"""Lesson 1 tests: the raw stdio exchange behaves as the lesson describes."""

import pytest
from wire import STEPS, exchange


@pytest.fixture(scope="module")
def responses() -> dict[int, dict]:
    return {r["id"]: r for r in exchange(STEPS)}


def test_discover_names_the_modern_protocol(responses):
    result = responses[1]["result"]
    assert result["supportedVersions"] == ["2026-07-28"]
    assert "tools" in result["capabilities"]


def test_every_result_carries_a_result_type(responses):
    for response in responses.values():
        if "result" in response:
            assert response["result"]["resultType"] == "complete"


def test_tools_list_is_cacheable(responses):
    result = responses[2]["result"]
    assert {"ttlMs", "cacheScope"} <= result.keys()
    assert [t["name"] for t in result["tools"]] == ["get_ticket", "ticket_count", "broken_report"]


def test_success_has_text_and_structured_content(responses):
    result = responses[3]["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["result"].startswith("HL-1003:")


def test_anticipated_error_reaches_the_model_with_its_hint(responses):
    result = responses[4]["result"]
    assert result["isError"] is True
    assert "Ticket ids look like HL-1003" in result["content"][0]["text"]


def test_crash_hides_internal_details(responses):
    text = responses[5]["result"]["content"][0]["text"]
    assert text == "Error executing tool broken_report"
    assert "db-primary" not in text


def test_unknown_tool_is_reported_as_a_tool_result_by_this_sdk(responses):
    # The spec lists "unknown tool" as a protocol error; mcp 2.3.0 returns a tool result.
    result = responses[6]["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == "Unknown tool: delete_everything"


def test_unknown_resource_is_a_protocol_error(responses):
    error = responses[7]["error"]
    assert error["code"] == -32602


def test_missing_argument_is_a_tool_result_error(responses):
    # Input validation failures are tool execution errors: the model can fix them.
    result = responses[8]["result"]
    assert result["isError"] is True
    assert "ticket_id\n  Field required" in result["content"][0]["text"]


def test_malformed_params_are_a_protocol_error(responses):
    # arguments must be an object: the request breaks the CallToolRequest schema.
    error = responses[9]["error"]
    assert error["code"] == -32602
    assert error["message"] == "Invalid request parameters"
