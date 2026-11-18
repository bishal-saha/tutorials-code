export const config = {
  databaseUrl: process.env.DATABASE_URL ?? 'postgres://rag_app:rag_app@localhost:5433/rag',
  ingestDatabaseUrl: process.env.DATABASE_URL_INGEST ?? 'postgres://rag_ingest:rag_ingest@localhost:5433/rag',
  adminDatabaseUrl: process.env.DATABASE_URL_ADMIN ?? 'postgres://rag:rag@localhost:5433/rag',
  embeddings: {
    provider: process.env.EMBEDDINGS_PROVIDER ?? 'fake',
    dimensions: Number(process.env.EMBEDDINGS_DIMENSIONS ?? 256),
    url: process.env.EMBEDDINGS_URL, model: process.env.EMBEDDINGS_MODEL, apiKey: process.env.EMBEDDINGS_API_KEY,
  },
  chunking: { maxWords: 120, overlapWords: 25 },
  jwt: {
    secret: process.env.JWT_SECRET,
    issuer: process.env.JWT_ISSUER ?? 'https://auth.example.test',
    audience: process.env.JWT_AUDIENCE ?? 'support-assistant',
  },
  answer: {
    k: Number(process.env.ANSWER_K ?? 5),
    maxDistance: Number(process.env.ANSWER_MAX_DISTANCE ?? 0.75),
    maxContextWords: Number(process.env.ANSWER_MAX_CONTEXT_WORDS ?? 600),
  },
  port: Number(process.env.PORT ?? 3000),
};
