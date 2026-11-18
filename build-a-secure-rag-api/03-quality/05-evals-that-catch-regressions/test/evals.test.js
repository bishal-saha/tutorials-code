import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { adminPool, endAll } from '../src/db.js';
import { runEvals, gate } from '../eval/run.js';
import { setup, embedder } from './helpers.js';

before(setup);
after(endAll);

test('the current code passes every eval, with no leaks', async () => {
  const report = await runEvals({ embedder });
  assert.deepEqual(report.leaks, []);
  assert.equal(report.scores.recallAtK, 1);
  assert.equal(report.scores.groundedness, 1);
  assert.equal(report.scores.noAnswerRate, 1);
});

test('a regression that drops the tenant filter and bypasses RLS fails the gate', async () => {
  // What a careless refactor looks like: the WHERE clause "simplified" away, and the query run on
  // a connection that row-level security doesn't apply to (here the superuser).
  const leaky = async (emb, principal, question, k) => {
    const [v] = await emb.embed([question]);
    const { rows } = await adminPool.query(
      `SELECT c.id, c.document_id, d.title, c.content, c.embedding <=> $1 AS distance
       FROM chunks c JOIN documents d ON d.id = c.document_id
       ORDER BY distance LIMIT $2`, [`[${v.join(',')}]`, k]);
    return rows.map((r) => ({ chunkId: Number(r.id), documentId: r.document_id, title: r.title, content: r.content, distance: Number(r.distance) }));
  };
  const report = await runEvals({ embedder, search: leaky });
  const baseline = { datasetVersion: report.datasetVersion, k: report.k, scores: { recallAtK: 1, groundedness: 1, noAnswerRate: 1 } };
  const { pass, failures } = gate(report, baseline);
  assert.equal(pass, false);
  assert.ok(failures.some((f) => f.startsWith('LEAK in probe-globex-agent-asks-acme-runbook')));
});

test('a quality drop beyond tolerance fails, and a small one passes', () => {
  const baseline = { datasetVersion: 5, k: 5, scores: { recallAtK: 1, groundedness: 1, noAnswerRate: 1 } };
  const report = (recallAtK) => ({ datasetVersion: 5, k: 5, probes: 3, leaks: [], scores: { recallAtK, groundedness: 1, noAnswerRate: 1 } });
  assert.equal(gate(report(0.96), baseline).pass, true);
  assert.equal(gate(report(0.8), baseline).pass, false);
});

test('a missing or non-numeric score fails the gate instead of passing silently', () => {
  const baseline = { datasetVersion: 5, k: 5, scores: { recallAtK: 1, groundedness: 1, noAnswerRate: 1 } };
  const report = { datasetVersion: 5, k: 5, probes: 3, leaks: [], scores: { recallAtK: NaN, groundedness: 1, noAnswerRate: 1 } };
  const { pass, failures } = gate(report, baseline);
  assert.equal(pass, false);
  assert.match(failures[0], /recallAtK is missing or not a number/);
});

test('a run at a different k than the baseline fails until re-baselined', () => {
  const baseline = { datasetVersion: 5, k: 5, scores: { recallAtK: 1, groundedness: 1, noAnswerRate: 1 } };
  const { pass, failures } = gate({ datasetVersion: 5, k: 2, probes: 3, leaks: [], scores: baseline.scores }, baseline);
  assert.equal(pass, false);
  assert.match(failures[0], /k=5/);
});

test('a probe whose forbidden document no longer exists stops the run instead of passing', async () => {
  const golden = { version: 5, k: 5, questions: [{ id: 'renamed-doc-probe', principal: { tenant: 'globex', roles: ['agent'] },
    question: 'stuck export', expect: { kind: 'isolation', forbidden: ['acme/renamed-runbook.md'], planted: ['ERR-7731'] } }] };
  await assert.rejects(runEvals({ embedder, golden }), /forbidden document acme\/renamed-runbook.md has no chunks/);
});

test('a run with no isolation probes fails the gate', () => {
  const baseline = { datasetVersion: 5, k: 5, scores: { recallAtK: 1, groundedness: 1, noAnswerRate: 1 } };
  const { pass, failures } = gate({ datasetVersion: 5, k: 5, probes: 0, leaks: [], scores: baseline.scores }, baseline);
  assert.equal(pass, false);
  assert.match(failures[0], /no isolation probes ran/);
});

test('a planted string that appears in its own probe question stops the run', async () => {
  const golden = { version: 6, k: 5, questions: [{ id: 'echo-probe', principal: { tenant: 'globex', roles: ['agent'] },
    question: 'The worker logs ERR-7731. How do I recover?', expect: { kind: 'isolation', forbidden: ['acme/exports-runbook.md'], planted: ['ERR-7731'] } }] };
  await assert.rejects(runEvals({ embedder, golden }), /planted string ERR-7731 appears in the question/);
});

test('an injection probe that never retrieves the planted document fails the gate', async () => {
  // A search that returns nothing leaks nothing; the positive control stops that from passing.
  const empty = async () => [];
  const report = await runEvals({ embedder, search: empty });
  assert.deepEqual(report.leaks, []);
  const { pass, failures } = gate(report, { datasetVersion: report.datasetVersion, k: report.k, scores: report.scores });
  assert.equal(pass, false);
  assert.ok(failures.some((f) => f.startsWith('PROBE probe-injected-instruction-in-globex-doc never retrieved globex/partner-note.md')));
});
