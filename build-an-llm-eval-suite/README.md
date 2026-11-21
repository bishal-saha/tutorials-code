# Build an eval suite for an LLM feature

> Code for the tutorial **[Build an eval suite for an LLM feature](https://iambishal.com/tutorials/build-an-llm-eval-suite)** on iambishal.com.
> Each lesson folder holds the complete, runnable code at the end of that lesson.

| | |
|---|---|
| Type | Tutorial (5 lessons) |
| Tested with | Python 3.12 · anthropic 2.12.0 · uv 0.12 · last verified 2026-11-21 |
| Tests | `uv run pytest` here runs every lesson's suite; or `uv run pytest tests` inside one lesson |
| Keys | none: every script replays recorded calls from `runs/calls.jsonl` by default. `--live` calls Claude and needs `ANTHROPIC_API_KEY` (see `.env.example`) |
| Models | drafter `claude-sonnet-5-5`; judges `claude-haiku-5-5` and `claude-sonnet-5-5`; effort `low`, structured output |

## Lessons

| # | Lesson | Folder | What it adds |
|---|---|---|---|
| 1 | Why reading outputs isn't an eval | `01-foundations/01-why-reading-outputs-isnt-an-eval` | `read_five.py`: five drafts that look fine, and the one failure that reading five would miss 7 times in 8 |
| 2 | A golden set and code graders | `01-foundations/02-a-golden-set-and-code-graders` | The drafter (structured output), a 40-case golden set, four code graders, a runner, record and replay |
| 3 | An LLM judge you can trust | `02-judging/03-an-llm-judge-you-can-trust` | A pass/fail judge, 60 labels known by construction, TPR/TNR/kappa, a sharpened criterion, repeats |
| 4 | Comparing two versions without fooling yourself | `02-judging/04-comparing-two-versions` | Prompt v2, paired splits, bootstrap intervals, sample size, judge shrinkage, pairwise swap test |
| 5 | Ship it: a regression gate and production sampling | `03-shipping/05-ship-it` | A CI gate with thresholds that replays judgements, a seeded regression, a review queue, a cost report |

The feature under test is the **Helpline reply drafter**: one Claude call that takes a support
ticket plus a 15-article knowledge base and returns `reply`, `cited_articles` and `escalate`.
Helpline is the made-up support desk from *Build a production MCP server* and *Build a bounded
agent*; every company, ticket and article here is synthetic.

The real runs (2026-11-21) are recorded in each lesson's `runs/calls.jsonl` and replayed by the
tests, so CI never calls the API. Recording the whole series cost about USD 0.58.

## Licence

MIT, see the repository's [LICENSE](../LICENSE).
