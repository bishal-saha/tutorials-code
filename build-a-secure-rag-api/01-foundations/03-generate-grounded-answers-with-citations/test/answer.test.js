// Needs a database: npm run db:up && DATABASE_URL=... npm test
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { pool } from '../src/db.js';
import { migrate } from '../scripts/migrate.js';
import { ingestAll } from '../scripts/ingest.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { createFakeLlm } from '../src/llm/fake.js';
import { answerQuestion, NO_ANSWER, uncitedSentences, parseCitations, hasStrayChunkRef } from '../src/answer.js';
import { buildPrompt, formatChunk } from '../src/prompt.js';
import { buildServer } from '../src/server.js';

const embedder = createEmbeddingProvider({ provider: 'fake', dimensions: 256 });
const llm = createFakeLlm();

before(async () => {
  await migrate();
  await ingestAll(undefined, embedder);
});
after(() => pool.end());

test('a matching question gets an answer with citations to retrieved chunks', async () => {
  const res = await answerQuestion({ embedder, llm }, 'How do I rotate an API key without downtime?');
  assert.equal(res.noAnswer, false);
  assert.match(res.answer, /\[chunk:\d+\]/);
  assert.equal(res.citations[0].title, 'Rotating API keys');
});

test('an unrelated question takes the no-answer path before any model call', async () => {
  let called = false;
  const spy = { generate: async (p) => { called = true; return llm.generate(p); } };
  const res = await answerQuestion({ embedder, llm: spy }, 'What is the weather in Lisbon tomorrow?');
  assert.equal(res.answer, NO_ANSWER);
  assert.equal(res.reason, 'no chunk within maxDistance');
  assert.equal(called, false);
});

test('a citation to a chunk that was not in the prompt is rejected', async () => {
  const inventing = { generate: async () => ({ text: 'Restart the worker. [chunk:99999]' }) };
  const res = await answerQuestion({ embedder, llm: inventing }, 'How do I rotate an API key?');
  assert.equal(res.noAnswer, true);
  assert.match(res.reason, /not in the context/);
});

test('an answer without any citation is rejected', async () => {
  const uncited = { generate: async () => ({ text: 'Just restart everything.' }) };
  const res = await answerQuestion({ embedder, llm: uncited }, 'How do I rotate an API key?');
  assert.equal(res.noAnswer, true);
});

test('the prompt keeps whole chunks inside the context budget', () => {
  const chunks = [1, 2, 3].map((i) => ({ chunkId: i, content: Array(50).fill(`w${i}`).join(' ') }));
  const prompt = buildPrompt('q', chunks, { maxContextWords: 120 });
  assert.deepEqual(prompt.included.map((c) => c.chunkId), [1, 2]);
  assert.equal(prompt.contextWords, 100);
});

test('a chunk too big for the budget is skipped, and smaller ones still fit', () => {
  const sized = (id, n) => ({ chunkId: id, content: Array(n).fill('w').join(' ') });
  const prompt = buildPrompt('q', [sized(1, 200), sized(2, 40), sized(3, 30)], { maxContextWords: 100 });
  assert.deepEqual(prompt.included.map((c) => c.chunkId), [2, 3]);
  assert.deepEqual(prompt.dropped, [1]);
});

test('each included chunk is formatted by formatChunk, with its id', () => {
  const chunk = { chunkId: 7, content: 'Revoke the old key.' };
  assert.equal(formatChunk(chunk), '<chunk id="7">\nRevoke the old key.\n</chunk>');
  assert.ok(buildPrompt('q', [chunk]).user.includes(formatChunk(chunk)));
});

test('only the system prompt and user message reach the model', async () => {
  let keys;
  const spy = { generate: async (p) => { keys = Object.keys(p); return llm.generate(p); } };
  await answerQuestion({ embedder, llm: spy }, 'How do I rotate an API key without downtime?');
  assert.deepEqual(keys, ['system', 'user']);
});

test('when no relevant chunk fits the budget, the model is not called', async () => {
  let called = false;
  const spy = { generate: async (p) => { called = true; return llm.generate(p); } };
  const res = await answerQuestion({ embedder, llm: spy }, 'How do I rotate an API key without downtime?', { maxContextWords: 5 });
  assert.equal(res.reason, 'no relevant chunk fits the context budget');
  assert.equal(called, false);
});

test('an answer with an uncited sentence is rejected', async () => {
  const partly = { generate: async ({ user }) => {
    const id = user.match(/<chunk id="(\d+)">/)[1];
    return { text: `Create a new key first. [chunk:${id}] Then just restart everything.` };
  } };
  const res = await answerQuestion({ embedder, llm: partly }, 'How do I rotate an API key?');
  assert.equal(res.reason, 'a sentence in the answer has no citation');
});

test('POST /answer returns the grounded answer', async () => {
  const app = buildServer({ embedder, llm });
  const res = await app.inject({ method: 'POST', url: '/answer', payload: { question: 'How do I change the billing contact email?' } });
  assert.equal(res.statusCode, 200);
  assert.equal(res.json().citations[0].title, 'Invoices and billing');
  await app.close();
});

test('every sentence needs its own citation, wherever it sits', () => {
  assert.equal(uncitedSentences('Create a key. [chunk:1] Revoke the old one. [chunk:2]'), false);
  assert.equal(uncitedSentences('Create a key. [chunk:1] [chunk:2]'), false);
  assert.equal(uncitedSentences('Create a key. Revoke the old one. [chunk:1]'), true); // uncited sentence before a cited one
  assert.equal(uncitedSentences('Create a key. [chunk:1] Then restart everything.'), true); // uncited sentence after
  assert.equal(uncitedSentences('1. Create a key. [chunk:1]\n2. Deploy it. [chunk:1]'), false); // a cited numbered list
  assert.equal(uncitedSentences('Create a key\nThen deploy it. [chunk:1]'), true); // an uncited line before a cited one
  assert.equal(uncitedSentences('Revoke the old key [chunk:9].'), true); // full stop after the citation: refused
});

test('citations are parsed tolerantly, and malformed ones are caught', () => {
  assert.deepEqual(parseCitations('A. [chunk:9] B. [Chunk: 8] C. [chunk 7] D. [chunk#6]').map((c) => c.id), ['9', '8', '7', '6']);
  assert.deepEqual(parseCitations('Restart it [chunk: abc].').map((c) => c.id), [null]);
  assert.deepEqual(parseCitations('Rotate it. [chunk:9, chunk:8]').map((c) => c.id), [null]); // grouped: malformed
});

test('a well-formed citation next to a malformed or invented one is refused', async () => {
  const sneaky = (cite) => ({ generate: async ({ user }) => {
    const id = user.match(/<chunk id="(\d+)">/)[1];
    return { text: `Restart the worker ${cite}. [chunk:${id}]` };
  } });
  for (const cite of ['[chunk: 99999]', '[chunk:abc]']) {
    const res = await answerQuestion({ embedder, llm: sneaky(cite) }, 'How do I rotate an API key?');
    assert.equal(res.noAnswer, true, cite);
  }
});

test('a correctly cited answer in a looser citation format is accepted', async () => {
  const loose = { generate: async ({ user }) => {
    const id = user.match(/<chunk id="(\d+)">/)[1];
    return { text: `Create a new key and deploy it. [Chunk: ${id}]` };
  } };
  const res = await answerQuestion({ embedder, llm: loose }, 'How do I rotate an API key?');
  assert.equal(res.noAnswer, false);
});

test('a chunk number outside the bracket form is refused', async () => {
  assert.equal(hasStrayChunkRef('Restart the worker (chunk 99999). [chunk:9]'), true);
  assert.equal(hasStrayChunkRef('See [chunks 4]. [chunk:9]'), true);
  assert.equal(hasStrayChunkRef('Create a new key. [chunk:9] Then revoke the old one. [Chunk: 8]'), false);
  const stray = { generate: async ({ user }) => {
    const id = user.match(/<chunk id="(\d+)">/)[1];
    return { text: `Restart the worker (chunk 99999). [chunk:${id}]` };
  } };
  const res = await answerQuestion({ embedder, llm: stray }, 'How do I rotate an API key?');
  assert.equal(res.reason, 'answer cited no chunk, or a chunk not in the context');
});
