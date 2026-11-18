// All configuration comes from the environment. Node 24 can load a .env file with --env-file.

// A positive number from the environment; a typo or empty value stops the process at startup.
const positive = (name, fallback) => {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be a positive number`);
  return value;
};

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
  answer: {
    k: positive('ANSWER_K', 5),
    maxDistance: positive('ANSWER_MAX_DISTANCE', 0.75),
    maxContextWords: positive('ANSWER_MAX_CONTEXT_WORDS', 600),
  },
  port: Number(process.env.PORT ?? 3000),
};
