# Lesson 4: Guardrails and a human approval gate

```bash
uv run pytest tests
```

| File | What it shows |
|---|---|
| `agent/guardrails.py` | Untrusted-data delimiting, task allowlist, scope check, draft checks |
| `agent/approval.py` | Approval gate for `escalate_ticket` and the append-only decision log |
| `data/helpline-with-injection.json` | Helpline's data plus `HL-1012`, a prompt-injection fixture |
