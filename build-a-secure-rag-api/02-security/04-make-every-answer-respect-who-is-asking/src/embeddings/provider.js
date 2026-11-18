import { config } from '../config.js';
import { createFakeEmbedder } from './fake.js';
import { createHttpEmbedder } from './http.js';

/**
 * The only contract ingest and search depend on.
 * @typedef {object} EmbeddingProvider
 * @property {number} dimensions  fixed vector length; the chunks.embedding column is created with it
 * @property {(texts: string[]) => Promise<number[][]>} embed  one vector per input, same order
 */

/** @returns {EmbeddingProvider} */
export function createEmbeddingProvider(options = config.embeddings) {
  // The fake is the default for local runs and tests; never let it reach production by accident.
  if (options.provider === 'fake' && process.env.NODE_ENV === 'production') throw new Error('EMBEDDINGS_PROVIDER=fake is not allowed in production');
  if (options.provider === 'fake') return createFakeEmbedder(options.dimensions);
  if (options.provider === 'http') return createHttpEmbedder(options);
  throw new Error(`Unknown EMBEDDINGS_PROVIDER: ${options.provider}`);
}
