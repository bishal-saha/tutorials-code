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
| _Coming soon_ | | |

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

Python 3.12+ and [uv](https://docs.astral.sh/uv/). API keys only where a `.env.example` asks for them; `.env` is never committed.

## Problems

Open an issue and say which series and lesson it's about.

## Licence

Code: [MIT](LICENSE). The tutorials themselves stay on iambishal.com.
