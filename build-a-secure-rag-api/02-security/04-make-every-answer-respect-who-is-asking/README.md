# Lesson 4: Make every answer respect who is asking

Complete code at the end of lesson 4 of [Build a secure RAG API](https://iambishal.com/tutorials/build-a-secure-rag-api).

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

`npm test` includes the cross-tenant probes (`test/isolation.test.js`) and the iterative-scan demonstration (`test/filter-and-iterative-scan.test.js`).
