import Fastify from 'fastify';
import { config } from './config.js';
import { createEmbeddingProvider } from './embeddings/provider.js';
import { createLlmProvider } from './llm/provider.js';
import { searchChunks } from './search.js';
import { answerQuestion } from './answer.js';

export function buildServer({ embedder = createEmbeddingProvider(), llm = createLlmProvider() } = {}) {
  const app = Fastify({ logger: false });
  app.get('/search', {
    schema: {
      querystring: {
        type: 'object', required: ['q'],
        properties: { q: { type: 'string', minLength: 1, maxLength: 1000 }, k: { type: 'integer', minimum: 1, maximum: 20, default: 5 } },
      },
    },
  }, async (req) => ({ query: req.query.q, results: await searchChunks(embedder, req.query.q, req.query.k) }));

  app.post('/answer', {
    schema: {
      body: {
        type: 'object', required: ['question'], additionalProperties: false,
        properties: { question: { type: 'string', minLength: 1, maxLength: 1000 } },
      },
    },
  }, async (req) => answerQuestion({ embedder, llm }, req.body.question, config.answer));
  return app;
}

if (import.meta.main) {
  const app = buildServer();
  await app.listen({ port: config.port });
  console.warn('WARNING: /search and /answer are unprotected and read every tenant\'s chunks (fixed in lesson 4).');
  console.log(`listening on http://localhost:${config.port}`);
}
