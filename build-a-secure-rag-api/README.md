# Build a secure RAG API

> Code for the tutorial **[Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api)** on iambishal.com.
> Each lesson folder holds the complete, runnable code at the end of that lesson.

| | |
|---|---|
| Type | Tutorial (5 lessons) |
| Tested with | Node.js 24.18 · PostgreSQL 17.12 · pgvector 0.8.7 · last verified 2026-11-18 |
| Run | `npm install && npm run db:up && npm run migrate && npm run ingest && npm start` (in a lesson folder) |
| Tests | `npm test` (needs the database from `npm run db:up`) |
| Keys | none: tests use a deterministic fake embedder and fake model; see `.env.example` to plug in real providers |

## Lessons

| # | Lesson | Folder | What it adds |
|---|---|---|---|
| 1 | How a RAG API answers, and where it leaks | `01-foundations/01-how-a-rag-api-answers-and-where-it-leaks` | Reading only: architecture and threat model |
| 2 | Ingest and search support documents with pgvector | `01-foundations/02-ingest-and-search-with-pgvector` | Schema, chunking, embeddings behind an interface, HNSW, `GET /search` (unprotected on purpose) |
| 3 | Generate grounded answers with citations | `01-foundations/03-generate-grounded-answers-with-citations` | `POST /answer`, prompt budget, no-answer threshold, citation checks |
| 4 | Make every answer respect who is asking | `02-security/04-make-every-answer-respect-who-is-asking` | JWT principal, transaction-scoped settings, RLS, filtered search with iterative scans, delimiting, cache keys, leak tests |
| 5 | Evals that catch regressions before users do | `03-quality/05-evals-that-catch-regressions` | Golden dataset, recall@k, groundedness, isolation probes, baseline gate, CI workflow |

Lessons 2 and 3 search every tenant's documents on purpose, to show the leak lesson 4 closes. Don't deploy them.
