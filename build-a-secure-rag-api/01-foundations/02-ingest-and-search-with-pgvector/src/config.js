// All configuration comes from the environment. Node 24 can load a .env file with --env-file.
export const config = {
  databaseUrl: process.env.DATABASE_URL ?? 'postgres://rag:rag@localhost:5433/rag',
  embeddings: {
    provider: process.env.EMBEDDINGS_PROVIDER ?? 'fake',
    dimensions: Number(process.env.EMBEDDINGS_DIMENSIONS ?? 256),
    url: process.env.EMBEDDINGS_URL,
    model: process.env.EMBEDDINGS_MODEL,
    apiKey: process.env.EMBEDDINGS_API_KEY,
  },
  chunking: { maxWords: 120, overlapWords: 25 },
  port: Number(process.env.PORT ?? 3000),
};
