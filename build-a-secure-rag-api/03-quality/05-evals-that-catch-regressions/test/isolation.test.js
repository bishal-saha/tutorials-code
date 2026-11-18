// The cross-tenant probe from lesson 1, run for real. Needs a database (see README).
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import pg from 'pg';
import { adminPool, endAll, toVector } from '../src/db.js';
import { config } from '../src/config.js';
import { withPrincipal } from '../src/tenant-session.js';
import { retrieve, searchByVector } from '../src/search.js';
import { answerQuestion } from '../src/answer.js';
import { createFakeLlm } from '../src/llm/fake.js';
import { setup, embedder, principal, chunkIdsOf } from './helpers.js';

const llm = createFakeLlm();
// Worded like acme's agent-only runbook, including its error code.
const PROBE = 'The export has been running for more than two hours and the worker logs ERR-7731. How do I recover the stuck export?';
let T; let acmeRunbook; let acmeHelp; let globexRunbook;

before(async () => {
  T = await setup();
  acmeRunbook = await chunkIdsOf('acme', 'exports-runbook.md');
  acmeHelp = await chunkIdsOf('acme', 'exports-help.md');
  globexRunbook = await chunkIdsOf('globex', 'exports-runbook.md');
});
after(endAll);

const ids = (rows) => rows.map((r) => r.chunkId);
const hits = (rows, set) => ids(rows).filter((id) => set.has(id));

test('negative control: unfiltered, as a role RLS does not restrict, the forbidden runbook is a top-5 neighbour', async () => {
  const [v] = await embedder.embed([PROBE]);
  const { rows } = await adminPool.query('SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 5', [toVector(v)]);
  assert.ok(rows.some((r) => acmeRunbook.has(Number(r.id))), 'the probe must really match the forbidden document');
});

test('forbidden probe 1: a globex agent never retrieves or cites acme chunks', async () => {
  const p = principal(T.globex, ['agent']);
  const rows = await retrieve(embedder, p, PROBE, 5);
  assert.deepEqual(hits(rows, acmeRunbook), []);
  const res = await answerQuestion({ embedder, llm }, p, PROBE);
  assert.ok(!res.citations.some((c) => acmeRunbook.has(c.chunkId)));
  assert.doesNotMatch(res.answer, /ERR-7731/);
});

test('forbidden probe 2: an acme end user never retrieves or cites the agent-only runbook', async () => {
  const p = principal(T.acme, ['end_user']);
  const rows = await retrieve(embedder, p, PROBE, 5);
  assert.deepEqual(hits(rows, acmeRunbook), []);
  const res = await answerQuestion({ embedder, llm }, p, PROBE);
  assert.doesNotMatch(res.answer, /ERR-7731/);
});

test('positive controls: legitimate callers do get the matching chunks', async () => {
  const agent = principal(T.acme, ['agent']);
  const asAgent = await answerQuestion({ embedder, llm }, agent, PROBE);
  assert.ok(asAgent.citations.some((c) => acmeRunbook.has(c.chunkId)), 'acme agent gets the runbook');

  const user = principal(T.acme, ['end_user']);
  const rows = await retrieve(embedder, user, 'An export failed with ERR-2210. How do I retry it?', 5);
  assert.ok(hits(rows, acmeHelp).length > 0, 'acme end user gets the help article');
});

test('RLS alone: with no WHERE clause, the app role still sees only its own tenant and roles', async () => {
  const p = principal(T.globex, ['agent']);
  const seen = await withPrincipal(p, async (c) => {
    const { rows } = await c.query('SELECT DISTINCT tenant_id, allowed_roles FROM chunks'); // deliberately unfiltered
    return rows;
  });
  assert.ok(seen.length > 0);
  assert.ok(seen.every((r) => r.tenant_id === T.globex && r.allowed_roles.includes('agent')));
  const endUser = principal(T.acme, ['end_user']);
  const acmeSeen = await withPrincipal(endUser, async (c) => (await c.query('SELECT id FROM chunks')).rows.map((r) => Number(r.id)));
  assert.deepEqual(acmeSeen.filter((id) => acmeRunbook.has(id) || globexRunbook.has(id)), []);
});

test('WHERE alone: as a role RLS does not restrict, the explicit filter still excludes foreign chunks', async () => {
  const p = principal(T.globex, ['agent']);
  const [v] = await embedder.embed([PROBE]);
  const client = await adminPool.connect(); // superuser: RLS does not apply, only the query's WHERE clause does
  try {
    const rows = await searchByVector(client, v, p, 5);
    assert.deepEqual(hits(rows, acmeRunbook), []);
  } finally {
    client.release();
  }
});

test('the app role is not the table owner and cannot bypass RLS', async () => {
  const { rows: [r] } = await adminPool.query(`
    SELECT rolbypassrls, rolsuper, (SELECT tableowner FROM pg_tables WHERE tablename = 'chunks') AS owner
    FROM pg_roles WHERE rolname = 'rag_app'`);
  assert.deepEqual(r, { rolbypassrls: false, rolsuper: false, owner: 'rag_owner' });
});

test('two tenants on one pooled connection: the principal ends with its transaction', async () => {
  // A pool of exactly one connection, so every checkout below gets the same server connection.
  const single = new pg.Pool({ connectionString: config.databaseUrl, max: 1 });
  try {
    // Request 1: an acme agent, through the real withPrincipal (BEGIN, set_config(..., true), COMMIT).
    const acme = await withPrincipal(principal(T.acme, ['agent']), async (c) =>
      (await c.query('SELECT pg_backend_pid() AS pid, count(*)::int AS n FROM chunks')).rows[0], single);

    // Between requests: check the same connection out directly, with no withPrincipal.
    const client = await single.connect();
    let left;
    try {
      ({ rows: [left] } = await client.query(`SELECT pg_backend_pid() AS pid,
        current_setting('app.tenant_id', true) AS tenant, (SELECT count(*)::int FROM chunks) AS n`));
    } finally {
      client.release();
    }
    console.log(`acme request, connection ${acme.pid}: ${acme.n} chunks visible`);
    console.log(`same connection after COMMIT: app.tenant_id=${JSON.stringify(left.tenant)}, ${left.n} chunks visible`);
    assert.equal(left.pid, acme.pid, 'the check ran on the same server connection');
    assert.ok(left.tenant === '' || left.tenant === null, 'no tenant is left on the connection');
    assert.equal(left.n, 0, 'fail closed: no principal, no rows');

    // Request 2: a globex agent on the same connection sees only globex.
    const globex = await withPrincipal(principal(T.globex, ['agent']), async (c) =>
      (await c.query('SELECT DISTINCT tenant_id, pg_backend_pid() AS pid FROM chunks')).rows, single);
    assert.equal(globex[0].pid, acme.pid);
    assert.deepEqual(globex.map((r) => r.tenant_id), [T.globex]);
  } finally {
    await single.end();
  }
});
