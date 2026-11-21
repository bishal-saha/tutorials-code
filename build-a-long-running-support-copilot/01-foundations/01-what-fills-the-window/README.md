# Lesson 1: What fills the window, and what actually goes wrong

```bash
uv run python window.py           # per-ticket window and cost, and what the last request carried
uv run python window.py --haiku   # the same at Haiku 5.5 prices
uv run pytest tests
```

| File | What it shows |
|---|---|
| `copilot/shift_data.py`, `data/shift.json` | The shift: 24 tickets and two standing instructions |
| `copilot/tools.py` | Five tools; `get_ticket` returns the bulk a real API returns |
| `copilot/model.py` | `ShiftModel` (scripted copilot), `CacheSim`, `AnthropicModel` |
| `copilot/shift.py` | `run_shift`: one conversation, every request priced |
| `copilot/grading.py` | Did the standing instructions hold? Checked from what the tools recorded |
| `window.py` | The window's make-up and cost, with and without caching |
