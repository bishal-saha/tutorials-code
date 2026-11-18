// Needs a database: npm run db:up && DATABASE_URL=... npm test
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { pool } from '../src/db.js';
import { migrate } from '../scripts/migrate.js';
import { ingestAll } from '../scripts/ingest.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { searchChunks } from '../src/search.js';
import { buildServer } from '../src/server.js';

const provider = createEmbeddingProvider({ provider: 'fake', dimensions: 256 });

before(async () => {
  await migrate();
  await ingestAll(undefined, provider);
});
after(() => pool.end());

test('every chunk carries its document tenant and ACL', async () => {
  const { rows } = await pool.query(`
    SELECT count(*)::int AS mismatches FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.tenant_id <> d.tenant_id OR c.allowed_roles <> d.allowed_roles`);
  assert.equal(rows[0].mismatches, 0);
});

test('an ACL change on a document reaches its chunks in the same statement', async () => {
  const { rows: [doc] } = await pool.query("SELECT id FROM documents WHERE source_key = 'api-keys-help.md'");
  await pool.query("UPDATE documents SET allowed_roles = '{agent}' WHERE id = $1", [doc.id]);
  const { rows } = await pool.query('SELECT DISTINCT allowed_roles FROM chunks WHERE document_id = $1', [doc.id]);
  assert.deepEqual(rows.map((r) => r.allowed_roles), [['agent']]);
  await pool.query("UPDATE documents SET allowed_roles = '{agent,end_user}' WHERE id = $1", [doc.id]);
});

test('re-ingesting a document replaces its chunks instead of adding to them', async () => {
  const before = (await pool.query('SELECT count(*)::int AS n FROM chunks')).rows[0].n;
  await ingestAll(undefined, provider);
  const after = (await pool.query('SELECT count(*)::int AS n FROM chunks')).rows[0].n;
  assert.equal(after, before);
});

test('the top-k query can use the HNSW index', async () => {
  const [v] = await provider.embed(['stuck export']);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL enable_seqscan = off'); // the table is tiny; force the planner to show the index path
    const { rows } = await client.query(
      'EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 5', [`[${v.join(',')}]`]);
    await client.query('ROLLBACK');
    assert.match(rows.map((r) => r['QUERY PLAN']).join('\n'), /Index Scan using chunks_embedding_hnsw/);
  } finally {
    client.release();
  }
});

test('search ranks the matching runbook first', async () => {
  const results = await searchChunks(provider, 'export stuck running for hours, how do I restart the export worker?', 3);
  assert.match(results[0].title, /stuck/i);
  assert.ok(results[0].distance < results[2].distance);
});

test('UNPROTECTED: search returns other tenants\' chunks (lesson 4 fixes this)', async () => {
  const results = await searchChunks(provider, 'export stuck running for hours, how do I restart the export worker?', 5);
  const tenants = new Set((await pool.query(
    'SELECT DISTINCT t.slug FROM documents d JOIN tenants t ON t.id = d.tenant_id WHERE d.id = ANY($1)',
    [results.map((r) => r.documentId)])).rows.map((r) => r.slug));
  assert.deepEqual([...tenants].sort(), ['acme', 'globex']);
});

test('GET /search returns ranked chunks with distances', async () => {
  const app = buildServer(provider);
  const res = await app.inject({ url: '/search?q=rotate%20api%20key&k=2' });
  assert.equal(res.statusCode, 200);
  const body = res.json();
  assert.equal(body.results.length, 2);
  assert.equal(body.results[0].title, 'Rotating API keys');
  await app.close();
});
