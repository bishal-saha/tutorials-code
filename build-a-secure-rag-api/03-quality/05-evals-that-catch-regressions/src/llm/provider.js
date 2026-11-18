import { createFakeLlm } from './fake.js';
import { createHttpLlm } from './http.js';

/**
 * The only contract the answer path depends on.
 * @typedef {object} LlmProvider
 * @property {(req: { system: string, user: string }) => Promise<{ text: string }>} generate
 */

/** @returns {LlmProvider} */
export function createLlmProvider(options = {
  provider: process.env.LLM_PROVIDER ?? 'fake',
  url: process.env.LLM_URL, model: process.env.LLM_MODEL, apiKey: process.env.LLM_API_KEY,
}) {
  // The fake is the default for local runs and tests; never let it reach production by accident.
  if (options.provider === 'fake' && process.env.NODE_ENV === 'production') throw new Error('LLM_PROVIDER=fake is not allowed in production');
  if (options.provider === 'fake') return createFakeLlm();
  if (options.provider === 'http') return createHttpLlm(options);
  throw new Error(`Unknown LLM_PROVIDER: ${options.provider}`);
}
