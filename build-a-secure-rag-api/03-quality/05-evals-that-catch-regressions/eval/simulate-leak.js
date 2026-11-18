// Runs the evals against a deliberately broken retrieval: the WHERE clause removed and the
// query run as the superuser, which row-level security doesn't apply to. The gate must fail.
//   node --env-file=.env eval/simulate-leak.js
import { readFile } from 'node:fs/promises';
import { adminPool, endAll, toVector } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { runEvals, gate } from './run.js';

const leaky = async (embedder, principal, question, k) => {
  const [v] = await embedder.embed([question]);
  const { rows } = await adminPool.query(
    `SELECT c.id, c.document_id, d.title, c.content, c.embedding <=> $1 AS distance
     FROM chunks c JOIN documents d ON d.id = c.document_id
     ORDER BY distance LIMIT $2`, [toVector(v), k]);
  return rows.map((r) => ({ chunkId: Number(r.id), documentId: r.document_id, title: r.title, content: r.content, distance: Number(r.distance) }));
};

const report = await runEvals({ embedder: createEmbeddingProvider(), search: leaky });
const baseline = JSON.parse(await readFile(new URL('./baseline.json', import.meta.url), 'utf8'));
const { pass, failures } = gate(report, baseline);
await endAll();
for (const f of failures) console.log(`FAIL ${f}`);
console.log(pass ? 'PASS' : 'FAIL');
process.exit(pass ? 0 : 1);
