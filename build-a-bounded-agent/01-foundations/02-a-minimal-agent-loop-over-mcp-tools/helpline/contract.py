"""Helpline's public contract, and a check that refuses breaking changes.

The contract is what clients and models depend on: tool names, input and output
schemas, annotations, required scopes and resource templates. It is captured
from the running server (not from source), committed as JSON, and compared in CI.

Breaking: anything that can make a call that worked yesterday fail, or a
response a client parsed yesterday unreadable. Additive: new things old clients
can ignore. A changed tool description is listed with the additive changes but
marked for review: the model reads descriptions as instructions, so a reviewer
should see every change to one (the gate cannot judge whether it is safe).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer

from helpline.auth import READ_SCOPE, TOOL_SCOPES

SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "helpline-contract.json"


def _inline(schema: Any, defs: dict[str, Any]) -> Any:
    """Resolve local $refs so two schemas compare by meaning, not by layout."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            return _inline(defs[schema["$ref"].split("/")[-1]], defs)
        return {k: _inline(v, defs) for k, v in schema.items() if k not in ("$defs", "title")}
    if isinstance(schema, list):
        return [_inline(v, defs) for v in schema]
    return schema


def _clean(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    return _inline(schema, schema.get("$defs", {}))


async def capture(server: MCPServer) -> dict[str, Any]:
    """The contract as a client sees it, with a stable key order."""
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        templates = (await client.list_resource_templates()).resource_templates
    return {
        "tools": {
            t.name: {
                # cleandoc: Python 3.13 strips docstring indentation at compile time and
                # 3.12 doesn't, so normalise or the snapshot depends on the interpreter.
                "description": inspect.cleandoc(t.description or ""),
                "input": _clean(t.input_schema),
                "output": _clean(t.output_schema),
                "read_only": bool(t.annotations and t.annotations.read_only_hint),
                "scopes": TOOL_SCOPES.get(t.name, [READ_SCOPE]),
            }
            for t in sorted(tools, key=lambda t: t.name)
        },
        "resource_templates": sorted(t.uri_template for t in templates),
    }


def _type(schema: dict[str, Any]) -> Any:
    if "anyOf" in schema:
        return sorted(json.dumps(_type(s), sort_keys=True) for s in schema["anyOf"])
    return schema.get("type")


def compare(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (breaking, additive) changes from old to new, as readable lines."""
    breaking: list[str] = []
    additive: list[str] = []

    for name in old["tools"].keys() - new["tools"].keys():
        breaking.append(f"tool {name}: removed")
    for name in new["tools"].keys() - old["tools"].keys():
        additive.append(f"tool {name}: added")

    for name in sorted(old["tools"].keys() & new["tools"].keys()):
        was, now = old["tools"][name], new["tools"][name]
        where = f"tool {name}"

        # Inputs: a call that was valid must stay valid.
        was_in, now_in = was["input"]["properties"], now["input"]["properties"]
        was_req = set(was["input"].get("required", []))
        now_req = set(now["input"].get("required", []))
        for arg in was_in.keys() - now_in.keys():
            breaking.append(f"{where}: input {arg} removed")
        for arg in now_req - was_req:
            breaking.append(f"{where}: input {arg} is now required")
        for arg in now_in.keys() - was_in.keys() - now_req:
            additive.append(f"{where}: optional input {arg} added")
        for arg in was_in.keys() & now_in.keys():
            a, b = was_in[arg], now_in[arg]
            if _type(a) != _type(b):
                breaking.append(f"{where}: input {arg} changed type")
            removed = set(_enum(a)) - set(_enum(b))
            if removed:
                breaking.append(f"{where}: input {arg} no longer accepts {sorted(removed)}")
            if b.get("maximum", float("inf")) < a.get("maximum", float("inf")):
                breaking.append(f"{where}: input {arg} maximum lowered")
            if b.get("minimum", float("-inf")) > a.get("minimum", float("-inf")):
                breaking.append(f"{where}: input {arg} minimum raised")

        # Outputs: a field a client read must still be there, with the same type.
        was_out = (was["output"] or {}).get("properties", {})
        now_out = (now["output"] or {}).get("properties", {})
        was_oreq = set((was["output"] or {}).get("required", []))
        now_oreq = set((now["output"] or {}).get("required", []))
        for fld in was_out.keys() - now_out.keys():
            breaking.append(f"{where}: output {fld} removed")
        for fld in was_oreq - now_oreq:
            breaking.append(f"{where}: output {fld} is no longer always present")
        for fld in was_out.keys() & now_out.keys():
            if _type(was_out[fld]) != _type(now_out[fld]):
                breaking.append(f"{where}: output {fld} changed type")
        for fld in now_out.keys() - was_out.keys():
            additive.append(f"{where}: output {fld} added")

        if was.get("description", "") != now.get("description", ""):
            additive.append(f"{where}: description changed (review it)")

        # Behaviour and permissions.
        if was["read_only"] and not now["read_only"]:
            breaking.append(f"{where}: was read-only, now writes")
        for scope in set(now["scopes"]) - set(was["scopes"]):
            breaking.append(f"{where}: now needs scope {scope}")

    for uri in set(old["resource_templates"]) - set(new["resource_templates"]):
        breaking.append(f"resource template {uri}: removed")
    for uri in set(new["resource_templates"]) - set(old["resource_templates"]):
        additive.append(f"resource template {uri}: added")
    return breaking, additive


def _enum(schema: dict[str, Any]) -> list[Any]:
    if "enum" in schema:
        return schema["enum"]
    return [v for s in schema.get("anyOf", []) for v in s.get("enum", [])]


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_snapshot(contract: dict[str, Any], path: Path = SNAPSHOT) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
