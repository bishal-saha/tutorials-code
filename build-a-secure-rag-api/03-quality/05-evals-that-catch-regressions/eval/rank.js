// Shows how one golden question ranks the chunks its principal may see, through the real
// retrieval path, and marks the chunks that hold its expected source with *.
//   node --env-file=.env eval/rank.js acme-agent-stuck-export [depth]
import { readFile } from 'node:fs/promises';
import { adminPool, endAll } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { retrieve } from '../src/answer.js';

const [id, depth = '8'] = process.argv.slice(2);
const golden = JSON.parse(await readFile(new URL('./golden.json', import.meta.url), 'utf8'));
const q = golden.questions.find((x) => x.id === id);
if (!q) throw new Error(`no question ${id} in golden.json`);
const { rows: [t] } = await adminPool.query('SELECT id FROM tenants WHERE slug = $1', [q.principal.tenant]);
const principal = { userId: `rank:${id}`, tenantId: t.id, roles: q.principal.roles };
const phrases = (q.expect.sources ?? []).map((s) => s.contains);

const rows = await retrieve(createEmbeddingProvider(), principal, q.question, Number(depth));
rows.forEach((r, i) => {
  const body = r.content.split('\n').slice(1).join(' ').trim(); // skip the heading path line
  const mark = phrases.some((p) => r.content.includes(p)) ? '*' : ' ';
  console.log(`${String(i + 1).padStart(2)}  ${r.distance.toFixed(4)} ${mark} ${body.slice(0, 60)}`);
});
await endAll();
