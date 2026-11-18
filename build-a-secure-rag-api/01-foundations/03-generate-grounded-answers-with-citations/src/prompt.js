// Prompt assembly with a context budget. Chunks are taken in rank order; one that doesn't
// fit in what's left is skipped (never cut in half, because half a procedure is worse than
// none) and smaller, lower-ranked chunks can still fill the space. Words are a rough,
// provider-neutral proxy for tokens.
export const SYSTEM_PROMPT = [
  'You answer questions for a customer support assistant.',
  'Use only the chunks inside <context>. Do not use outside knowledge.',
  'After every sentence, cite the chunk it came from as [chunk:ID], using an id from <context>.',
  'Put the full stop first and one id per bracket, for example: Revoke the old key. [chunk:9]',
  'If the chunks do not contain the answer, reply with exactly NO_ANSWER.',
].join('\n');

const countWords = (s) => s.split(/\s+/).filter(Boolean).length;

// How one chunk appears in the prompt. Lesson 4 replaces this function to delimit untrusted text.
export const formatChunk = (c) => `<chunk id="${c.chunkId}">\n${c.content}\n</chunk>`;

export function buildPrompt(question, chunks, { maxContextWords = 600 } = {}) {
  const included = [];
  const dropped = [];
  let used = 0;
  for (const chunk of chunks) {
    const n = countWords(chunk.content);
    if (used + n > maxContextWords) { dropped.push(chunk.chunkId); continue; }
    included.push(chunk);
    used += n;
  }
  const context = included.map(formatChunk).join('\n');
  const user = `<context>\n${context}\n</context>\n\n<question>\n${question}\n</question>`;
  return { system: SYSTEM_PROMPT, user, included, dropped, contextWords: used };
}
