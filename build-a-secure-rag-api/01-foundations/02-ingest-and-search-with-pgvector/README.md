# Lesson 2: Ingest and search support documents with pgvector

Complete code at the end of lesson 2 of [Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api).

```bash
cp .env.example .env
npm install
npm run db:up                  # PostgreSQL 17 + pgvector 0.8.7 in Docker on port 5433
node --env-file=.env scripts/migrate.js
node --env-file=.env scripts/ingest.js
docker compose exec -T db psql -U rag -d rag < scripts/inspect-chunks.sql   # chunk sizes per document
docker compose exec -T db psql -U rag -d rag < scripts/explain-search.sql   # the search query's plan
node --env-file=.env --test --test-concurrency=1
node --env-file=.env src/server.js
npm run db:down                # remove the container and its data
```
