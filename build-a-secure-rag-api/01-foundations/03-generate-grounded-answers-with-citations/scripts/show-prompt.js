// Prints what the answer path would send to the model for one question, and which chunks a
// given context budget keeps. No model is called.
//   node scripts/show-prompt.js "How do I rotate an API key without downtime?" 600 40
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { searchChunks } from '../src/search.js';
import { buildPrompt } from '../src/prompt.js';
import { config } from '../src/config.js';
import { pool } from '../src/db.js';

const [question, ...budgets] = process.argv.slice(2);
const words = (s) => s.split(/\s+/).filter(Boolean).length;
const relevant = (await searchChunks(createEmbeddingProvider(), question, config.answer.k))
  .filter((c) => c.distance <= config.answer.maxDistance);
console.log('candidates:', relevant.map((c) => `chunk ${c.chunkId} (${words(c.content)} words, distance ${c.distance})`).join(', '));
for (const budget of budgets.map(Number)) {
  const p = buildPrompt(question, relevant, { maxContextWords: budget });
  console.log(`\nmaxContextWords ${budget}: included [${p.included.map((c) => c.chunkId).join(', ')}], dropped [${p.dropped.join(', ')}], ${p.contextWords} words`);
  if (budget === Number(budgets[0])) console.log(p.user);
}
await pool.end();
