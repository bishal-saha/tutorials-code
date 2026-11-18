import Fastify from 'fastify';
import { config } from './config.js';
import { createEmbeddingProvider } from './embeddings/provider.js';
import { searchChunks } from './search.js';

export function buildServer(provider = createEmbeddingProvider()) {
  const app = Fastify({ logger: false });
  app.get('/search', {
    schema: {
      querystring: {
        type: 'object',
        required: ['q'],
        properties: {
          q: { type: 'string', minLength: 1, maxLength: 1000 },
          k: { type: 'integer', minimum: 1, maximum: 20, default: 5 },
        },
      },
    },
  }, async (req) => ({ query: req.query.q, results: await searchChunks(provider, req.query.q, req.query.k) }));
  return app;
}

if (import.meta.main) {
  const app = buildServer();
  await app.listen({ port: config.port });
  console.warn('WARNING: /search is unprotected and returns every tenant\'s chunks (fixed in lesson 4).');
  console.log(`listening on http://localhost:${config.port}`);
}
