// Shows why a filtered HNSW query can return fewer than k rows, and how iterative index
// scans fix it. Adds 3,000 synthetic chunks for a third tenant so acme becomes a small share.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { adminPool, ingestPool, endAll, toVector } from '../src/db.js';
import { setup, embedder } from './helpers.js';

let T;
before(async () => {
  T = await setup();
  const { rows: [bulk] } = await ingestPool.query("INSERT INTO tenants (slug, name) VALUES ('bulk', 'Bulk') RETURNING id");
  const { rows: [doc] } = await ingestPool.query(
    "INSERT INTO documents (tenant_id, source_key, title, allowed_roles) VALUES ($1, 'bulk.md', 'Bulk', '{agent}') RETURNING id", [bulk.id]);
  const texts = Array.from({ length: 3000 }, (_, i) => `export worker queue restart retry ${i} filler text number ${i % 97}`);
  const vectors = await embedder.embed(texts);
  for (let i = 0; i < texts.length; i += 500) {
    const values = []; const params = [];
    for (let j = i; j < Math.min(i + 500, texts.length); j++) {
      const n = params.length;
      values.push(`($${n + 1}, $${n + 2}, '{agent}', $${n + 3}, $${n + 4}, $${n + 5})`);
      params.push(doc.id, bulk.id, j, texts[j], toVector(vectors[j]));
    }
    await ingestPool.query(`INSERT INTO chunks (document_id, tenant_id, allowed_roles, chunk_index, content, embedding) VALUES ${values.join(',')}`, params);
  }
  await adminPool.query('ANALYZE chunks');
});
after(endAll);

const K = 9; // acme has exactly 9 chunks, so a complete answer returns all of them

async function filteredTopK(mode) {
  const [v] = await embedder.embed(['stuck export worker restart']);
  const client = await adminPool.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL enable_seqscan = off');           // make sure the HNSW index is used
    await client.query('SET LOCAL hnsw.ef_search = 40');           // the default, stated explicitly
    await client.query(`SET LOCAL hnsw.iterative_scan = '${mode}'`);
    const { rows } = await client.query(
      'SELECT id FROM chunks WHERE tenant_id = $2 ORDER BY embedding <=> $1 LIMIT $3', [toVector(v), T.acme, K]);
    await client.query('COMMIT');
    return rows.length;
  } finally {
    client.release();
  }
}

test('without iterative scans, the filtered query returns fewer than k rows', async () => {
  const n = await filteredTopK('off');
  console.log(`iterative_scan=off: ${n} of ${K} rows`);
  assert.ok(n < K);
});

test('strict_order scans further but can still stop short', async () => {
  const n = await filteredTopK('strict_order');
  console.log(`iterative_scan=strict_order: ${n} of ${K} rows`);
  assert.ok(n > 0 && n <= K);
});

test('relaxed_order returns all k rows', async () => {
  const n = await filteredTopK('relaxed_order');
  console.log(`iterative_scan=relaxed_order: ${n} of ${K} rows`);
  assert.equal(n, K);
});
