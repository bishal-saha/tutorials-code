import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chunkMarkdown } from '../src/chunker.js';

test('chunks keep whole paragraphs and carry their heading path', () => {
  const md = '## Steps\n\n1. One.\n\n2. Two.\n\n## Later\n\nThree.';
  const chunks = chunkMarkdown('Guide', md, { maxWords: 120, overlapWords: 25 });
  assert.deepEqual(chunks, ['Guide > Steps\n\n1. One.\n\n2. Two.', 'Guide > Later\n\nThree.']);
});

test('a section longer than maxWords splits with paragraph overlap', () => {
  const para = (n) => Array.from({ length: 30 }, (_, i) => `w${n}x${i}`).join(' ');
  const md = [para(1), para(2), para(3), para(4)].join('\n\n');
  const chunks = chunkMarkdown('Doc', md, { maxWords: 70, overlapWords: 30 });
  assert.equal(chunks.length, 3);
  assert.ok(chunks[1].includes('w2x0'), 'paragraph 2 is repeated at the start of chunk 2');
});
