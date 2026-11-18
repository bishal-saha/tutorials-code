import Fastify from 'fastify';
import { config } from './config.js';
import { createEmbeddingProvider } from './embeddings/provider.js';
import { createLlmProvider } from './llm/provider.js';
import { verifyPrincipal } from './auth.js';
import { retrieve } from './search.js';
import { answerQuestion } from './answer.js';

export function buildServer({ embedder = createEmbeddingProvider(), llm = createLlmProvider(), jwtKey } = {}) {
  // Fastify's validator strips unknown fields by default; reject them instead, so a client
  // that sends tenant_id learns it is not accepted.
  const app = Fastify({ logger: false, ajv: { customOptions: { removeAdditional: false } } });

  // Every route needs a verified principal. Nothing in the body or query can set it.
  app.decorateRequest('principal', null);
  app.addHook('onRequest', async (req, reply) => {
    const token = req.headers.authorization?.match(/^Bearer (.+)$/)?.[1];
    try {
      if (!token) throw new Error('missing bearer token');
      req.principal = await verifyPrincipal(token, jwtKey);
    } catch {
      return reply.code(401).send({ error: 'unauthorized' });
    }
  });

  app.get('/search', {
    schema: {
      querystring: {
        type: 'object', required: ['q'], additionalProperties: false,
        properties: { q: { type: 'string', minLength: 1, maxLength: 1000 }, k: { type: 'integer', minimum: 1, maximum: 20, default: 5 } },
      },
    },
  }, async (req) => ({
    query: req.query.q,
    results: await retrieve(embedder, req.principal, req.query.q, req.query.k),
  }));

  app.post('/answer', {
    schema: {
      body: { type: 'object', required: ['question'], additionalProperties: false, properties: { question: { type: 'string', minLength: 1, maxLength: 1000 } } },
    },
  }, async (req) => answerQuestion({ embedder, llm }, req.principal, req.body.question, config.answer));
  return app;
}

if (import.meta.main) {
  if (!config.jwt.secret) throw new Error('JWT_SECRET is required');
  const app = buildServer();
  await app.listen({ port: config.port });
  console.log(`listening on http://localhost:${config.port}`);
}
