# Lesson 3: Generate grounded answers with citations

Complete code at the end of lesson 3 of [Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api).

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
