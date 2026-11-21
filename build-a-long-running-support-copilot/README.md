# Build a long-running support copilot

> Code for the tutorial **[Build a long-running support copilot](https://iambishal.com/tutorials/build-a-long-running-support-copilot)** on iambishal.com.
> Each lesson folder holds the complete, runnable code at the end of that lesson.

| | |
|---|---|
| Type | Tutorial (5 lessons) |
| Tested with | Python 3.12 · anthropic 2.12.0 · uv 0.12 · last verified 2026-11-21 |
| Run | `uv sync`, then the scripts listed in each lesson's README |
| Tests | `uv run pytest` here runs every lesson's suite; or `uv run pytest tests` inside one lesson |
| Keys | none for tests, demos and the gate: a scripted copilot stands in for Claude. `live_shift.py` (lesson 5) calls Claude and needs `ANTHROPIC_API_KEY` |

## Lessons

| # | Lesson | Folder | What it adds |
|---|---|---|---|
| 1 | What fills the window, and what actually goes wrong | `01-foundations/01-what-fills-the-window` | A 24-ticket shift in one conversation; `window.py` shows what the window carries and what it costs |
| 2 | Lay out the prompt for the cache | `01-foundations/02-lay-out-the-prompt-for-the-cache` | Stable-to-volatile layout, `stable_tools()`, operator notes as mid-conversation system messages |
| 3 | Trim at the tool boundary, clear with honest placeholders | `02-managing-the-window/03-trim-and-clear` | Per-tool trimmers, the `clear` policy, honest vs misleading placeholders, server-side `clear_tool_uses` |
| 4 | Summaries, compaction and memory across shifts | `02-managing-the-window/04-summaries-compaction-and-memory` | Running summaries with pinned instructions, fresh windows, compaction (beta), the memory tool |
| 5 | Pick a policy with numbers | `03-production/05-pick-a-policy-with-numbers` | A harness comparing policies, `policy.json`, and the `check_policy.py` CI gate |

## How the scripted copilot works

`copilot/model.py` holds `ShiftModel`, a copilot that reacts only to what is in its window
(it keeps a standing instruction only while the instruction is visible), and `CacheSim`,
which works out cache reads and writes from each request's own bytes. It reproduces the
behaviours AI Lab experiment 7 (*Ticket Thirty*) observed with real models, so every lesson's
failure is a real consequence of what the window holds. It is a model, not Claude: use
`live_shift.py` to check your own numbers.

Helpline is a made-up support desk; every company, person and ticket in `data/shift.json`
is synthetic.

## Licence

MIT, see the repository's [LICENSE](../LICENSE).
