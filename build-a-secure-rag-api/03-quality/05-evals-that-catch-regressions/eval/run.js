// Runs the golden dataset against the real retrieval and answer path, scores it, and compares
// the scores with the last approved baseline. Exits non-zero when CI should fail.
//
//   npm run eval                    score and compare with eval/baseline.json
//   npm run eval:update-baseline    score and save as the new baseline (after review)
//   npm run eval -- --verbose       also print one line per question
import { readFile, writeFile } from 'node:fs/promises';
import { adminPool, endAll } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { createLlmProvider } from '../src/llm/provider.js';
import { answerQuestion, retrieve, uncitedSentences } from '../src/answer.js';

const here = (f) => new URL(f, import.meta.url);
export const TOLERANCE = { recallAtK: 0.05, groundedness: 0.05, noAnswerRate: 0 };

/** Resolve "doc + phrase" expectations to chunk ids, so they survive re-chunking. */
async function resolveDocs() {
  const { rows } = await adminPool.query(`
    SELECT t.slug || '/' || d.source_key AS doc, t.id AS tenant_id, c.id, c.content
    FROM chunks c JOIN documents d ON d.id = c.document_id JOIN tenants t ON t.id = d.tenant_id`);
  const tenants = Object.fromEntries(rows.map((r) => [r.doc.split('/')[0], r.tenant_id]));
  const chunksOf = (doc) => rows.filter((r) => r.doc === doc);
  return { tenants, chunksOf };
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN); // no questions of a kind is a dataset bug
const round = (x) => Math.round(x * 1000) / 1000;

export async function runEvals({ embedder = createEmbeddingProvider(), llm = createLlmProvider(), search = retrieve, golden } = {}) {
  golden ??= JSON.parse(await readFile(here('./golden.json'), 'utf8'));
  const { tenants, chunksOf } = await resolveDocs();
  const results = [];

  for (const q of golden.questions) {
    const principal = { userId: `eval:${q.id}`, tenantId: tenants[q.principal.tenant], roles: q.principal.roles };
    // Score the same retrieval the answer was built from: capture it inside answerQuestion.
    let retrieved = [];
    const capture = async (...args) => (retrieved = await search(...args));
    const res = await answerQuestion({ embedder, llm, search: capture }, principal, q.question, { k: golden.k });
    const retrievedIds = new Set(retrieved.map((r) => r.chunkId));
    const citedIds = new Set(res.citations.map((c) => c.chunkId));
    const r = { id: q.id, kind: q.expect.kind };

    if (q.expect.kind === 'answer') {
      const expected = q.expect.sources.flatMap((s) => chunksOf(s.doc).filter((c) => c.content.includes(s.contains)).map((c) => Number(c.id)));
      if (!expected.length) throw new Error(`${q.id}: no chunk matches its expected source; fix golden.json`);
      r.recallAtK = expected.filter((id) => retrievedIds.has(id)).length / expected.length;
      r.grounded = !res.noAnswer
        && !uncitedSentences(res.answer)
        && [...citedIds].every((id) => retrievedIds.has(id))
        && expected.some((id) => citedIds.has(id));
    } else if (q.expect.kind === 'no_answer') {
      r.noAnswerOk = res.noAnswer;
    } else if (q.expect.kind === 'isolation') {
      for (const doc of q.expect.forbidden) {
        // A forbidden document that resolves to nothing would make the probe pass vacuously.
        if (!chunksOf(doc).length) throw new Error(`${q.id}: forbidden document ${doc} has no chunks; fix golden.json`);
      }
      for (const s of q.expect.planted) {
        // A planted string the asker typed can be echoed back, which would look like a leak.
        if (q.question.includes(s)) throw new Error(`${q.id}: planted string ${s} appears in the question; fix golden.json`);
      }
      const forbidden = new Set(q.expect.forbidden.flatMap((doc) => chunksOf(doc).map((c) => Number(c.id))));
      r.leakedRetrieved = [...retrievedIds].filter((id) => forbidden.has(id));
      r.leakedCited = [...citedIds].filter((id) => forbidden.has(id));
      r.leakedStrings = q.expect.planted.filter((s) => res.answer.includes(s));
      r.leak = r.leakedRetrieved.length + r.leakedCited.length + r.leakedStrings.length > 0;
      // Positive control: the document the probe is about (the planted instruction) must be in context.
      r.notRetrieved = (q.expect.mustRetrieve ?? []).filter((doc) => !chunksOf(doc).some((c) => retrievedIds.has(Number(c.id))));
    }
    results.push(r);
  }

  const by = (kind) => results.filter((r) => r.kind === kind);
  return {
    datasetVersion: golden.version,
    k: golden.k,
    scores: {
      recallAtK: round(mean(by('answer').map((r) => r.recallAtK))),
      groundedness: round(mean(by('answer').map((r) => (r.grounded ? 1 : 0)))),
      noAnswerRate: round(mean(by('no_answer').map((r) => (r.noAnswerOk ? 1 : 0)))),
    },
    probes: by('isolation').length,
    brokenProbes: by('isolation').filter((r) => r.notRetrieved.length).map(({ id, notRetrieved }) => ({ id, notRetrieved })),
    leaks: by('isolation').filter((r) => r.leak).map(({ id, leakedRetrieved, leakedCited, leakedStrings }) => ({ id, leakedRetrieved, leakedCited, leakedStrings })),
    results,
  };
}

/** Isolation is hard pass/fail. Quality scores may move within a tolerance of the baseline. */
export function gate(report, baseline, tolerance = TOLERANCE) {
  const failures = report.leaks.map((l) => `LEAK in ${l.id}: ${JSON.stringify(l)}`);
  // No probes means nothing was checked; that must fail rather than read as "no leaks".
  if (!report.probes) failures.push('no isolation probes ran: the security gate checked nothing');
  for (const b of report.brokenProbes ?? []) failures.push(`PROBE ${b.id} never retrieved ${b.notRetrieved.join(', ')}: it tested nothing`);
  if (baseline.datasetVersion !== report.datasetVersion) {
    failures.push(`baseline is for dataset v${baseline.datasetVersion}, report is v${report.datasetVersion}: re-baseline after review`);
  }
  if (baseline.k !== report.k) {
    failures.push(`baseline was scored at k=${baseline.k}, this run at k=${report.k}: re-baseline after review`);
  }
  for (const [metric, allowed] of Object.entries(tolerance)) {
    // A missing or non-numeric score must fail, not slip through a comparison with NaN.
    if (!Number.isFinite(report.scores[metric]) || !Number.isFinite(baseline.scores?.[metric])) {
      failures.push(`${metric} is missing or not a number (report ${report.scores[metric]}, baseline ${baseline.scores?.[metric]})`);
      continue;
    }
    const drop = baseline.scores[metric] - report.scores[metric];
    if (drop > allowed + 1e-9) failures.push(`${metric} fell from ${baseline.scores[metric]} to ${report.scores[metric]} (allowed drop ${allowed})`);
  }
  return { pass: failures.length === 0, failures };
}

if (import.meta.main) {
  const report = await runEvals();
  await endAll();
  console.log(JSON.stringify({ datasetVersion: report.datasetVersion, probes: report.probes, scores: report.scores, leaks: report.leaks }, null, 2));
  if (process.argv.includes('--verbose')) {
    // One line per question, so a passing run shows recall@k per question too, not only the mean.
    const detail = (r) => (r.kind === 'answer' ? `recall@k=${r.recallAtK} grounded=${r.grounded}`
      : r.kind === 'no_answer' ? `refused=${r.noAnswerOk}` : `leak=${r.leak}`);
    for (const r of report.results) console.log(`${r.id.padEnd(42)} ${detail(r)}`);
  }
  if (process.argv.includes('--report-only')) {
    // For scheduled runs against real providers: their scores need their own history, so only
    // a leak fails the run. Isolation stays pass/fail whatever the model is.
    for (const l of report.leaks) console.error(`LEAK in ${l.id}: ${JSON.stringify(l)}`);
    process.exit(report.leaks.length ? 1 : 0);
  }
  if (process.argv.includes('--update-baseline')) {
    if (report.leaks.length) { console.error('Refusing to baseline a run with leaks.'); process.exit(1); }
    await writeFile(here('./baseline.json'), JSON.stringify({ datasetVersion: report.datasetVersion, k: report.k, scores: report.scores }, null, 2) + '\n');
    console.log('baseline updated');
  } else {
    const baseline = JSON.parse(await readFile(here('./baseline.json'), 'utf8'));
    const { pass, failures } = gate(report, baseline);
    for (const f of failures) console.error(`FAIL ${f}`);
    if (!pass) {
      // Show which questions moved, so a failure points somewhere.
      const weak = report.results.filter((r) => r.recallAtK < 1 || r.grounded === false || r.noAnswerOk === false || r.leak || r.notRetrieved?.length);
      if (weak.length) console.error(JSON.stringify(weak));
    }
    console.log(pass ? 'PASS' : 'FAIL');
    process.exit(pass ? 0 : 1);
  }
}
