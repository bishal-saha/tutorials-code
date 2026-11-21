# tutorials-code

Lesson-by-lesson code for the tutorial series on **[iambishal.com/tutorials](https://iambishal.com/tutorials)**.

Each series has one folder, named after its URL slug. Inside it, every lesson has its own folder holding the **complete, runnable code at the end of that lesson**, so you can start from any lesson.

```
<series-slug>/
├── README.md              # the series, with a link to every lesson
├── pyproject.toml         # one environment for the whole series
├── 01-<module-slug>/
│   ├── 01-<lesson-slug>/
│   └── 02-<lesson-slug>/
└── project/               # the series' running project, when it has one
```

## Series

| Series | Folder | Lessons |
|---|---|---|
| [Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api) | [`build-a-secure-rag-api`](build-a-secure-rag-api) | 5 (Node.js 24, PostgreSQL 17 + pgvector) |
| [Build a production MCP server](https://iambishal.com/tutorials/build-a-production-mcp-server) | [`build-a-production-mcp-server`](build-a-production-mcp-server) | 5 (Python 3.12, mcp 2.3.0) |
| [Build a bounded agent](https://iambishal.com/tutorials/build-a-bounded-agent) | [`build-a-bounded-agent`](build-a-bounded-agent) | 5 (Python 3.12, anthropic 2.12.0, mcp 2.3.0) |
| [Build an eval suite for an LLM feature](https://iambishal.com/tutorials/build-an-llm-eval-suite) | [`build-an-llm-eval-suite`](build-an-llm-eval-suite) | 5 (Python 3.12, anthropic 2.12.0) |

## Use one series

```bash
git clone --filter=blob:none --sparse https://github.com/bishal-saha/tutorials-code
cd tutorials-code
git sparse-checkout set <series-slug>
cd <series-slug>
uv sync && uv run pytest
```

Each finished series is also on the [Releases](https://github.com/bishal-saha/tutorials-code/releases) page as a zip.

## Requirements

Python 3.12+ and [uv](https://docs.astral.sh/uv/), unless the series' README says otherwise (Build a secure RAG API uses Node.js 24 and Docker). API keys only where a `.env.example` asks for them; `.env` is never committed.

## Problems

Open an issue and say which series and lesson it's about.

## Licence

Code: [MIT](LICENSE). The tutorials themselves stay on iambishal.com.
