# Lesson 5: Evals that catch regressions before users do

Complete code at the end of lesson 5 of [Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api).

```bash
cp .env.example .env
npm install
npm run db:up                  # PostgreSQL 17 + pgvector 0.8.7 in Docker on port 5433
node --env-file=.env scripts/migrate.js
node --env-file=.env scripts/ingest.js
node --env-file=.env --test --test-concurrency=1
node --env-file=.env src/server.js
npm run db:down                # remove the container and its data
```

Evals: `node --env-file=.env eval/run.js` (compare with `eval/baseline.json`; add `--verbose` for one line per question), `eval/simulate-leak.js` (a deliberately broken retrieval that must fail the gate) and `eval/rank.js <question-id>` (how one golden question ranks its principal's chunks). `ci/evals.yml` is the GitHub Actions workflow to copy into `.github/workflows/`; `ci/evals-nightly.yml` is the real-model template.
