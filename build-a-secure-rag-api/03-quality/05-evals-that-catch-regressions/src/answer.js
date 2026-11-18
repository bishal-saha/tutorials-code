import { retrieve } from './search.js';
import { buildPrompt } from './prompt.js';

/**
 * True when any sentence lacks a citation. The text between two citations (or before the
 * first) must be exactly one sentence, and nothing may follow the last citation. A sentence
 * boundary is . ! or ? after a letter or closing bracket, or a line break, so list markers
 * such as "2." don't count as sentences of their own.
 */
const SENTENCE_BOUNDARY = /(?<=[A-Za-z)"'][.!?])\s+\S|\n\s*\S/;

// Anything that looks like a citation, in any spacing or case: [chunk:9], [Chunk: 9], [chunk 9], [chunk:abc].
const CITATION_LIKE = /\[\s*chunk\b[^\]]*\]/gi;
// The forms accepted as a citation: "chunk", optional ":" or "#", then an id.
const CITATION = /^\[\s*chunk\s*[:#]?\s*(\d+)\s*\]$/i;

/** Every citation-like token with its parsed id, or null when it is malformed. */
export function parseCitations(text) {
  return [...text.matchAll(CITATION_LIKE)].map((m) => ({ token: m[0], id: m[0].match(CITATION)?.[1] ?? null }));
}

// A chunk number outside the bracket form, such as "(chunk 99999)" or "[chunks 4]". Never accepted.
const STRAY_CHUNK_REF = /\bchunks?\s*[:#]?\s*\d/i;
export const hasStrayChunkRef = (text) => STRAY_CHUNK_REF.test(text.replace(CITATION_LIKE, ' '));

export function uncitedSentences(text) {
  const pieces = text.trim().split(/[ \t]*\[\s*chunk\b[^\]]*\][ \t]*/i);
  const afterLast = pieces.pop();
  if (afterLast.trim() !== '') return true;
  return pieces.some((p) => SENTENCE_BOUNDARY.test(p.trim()));
}

export const NO_ANSWER = "I don't have enough information to answer that.";

/** Retrieve what this principal may see, then generate an answer grounded in it. */
// The default retrieval (lesson 4): embed, then the filtered query inside the principal's transaction.
export { retrieve };

export async function answerQuestion({ embedder, llm, search = retrieve }, principal, question, { k = 5, maxDistance = 0.75, maxContextWords = 600 } = {}) {
  const retrieved = await search(embedder, principal, question, k);
  const relevant = retrieved.filter((c) => c.distance <= maxDistance);
  if (!relevant.length) return { answer: NO_ANSWER, noAnswer: true, reason: 'no chunk within maxDistance', citations: [] };

  const prompt = buildPrompt(question, relevant, { maxContextWords });
  if (!prompt.included.length) return { answer: NO_ANSWER, noAnswer: true, reason: 'no relevant chunk fits the context budget', citations: [] };
  const { text } = await llm.generate({ system: prompt.system, user: prompt.user });
  if (text.trim() === 'NO_ANSWER') return { answer: NO_ANSWER, noAnswer: true, reason: 'model found no answer in context', citations: [] };

  const byId = new Map(prompt.included.map((c) => [String(c.chunkId), c]));
  const tokens = parseCitations(text);
  // A malformed citation-like token is treated like an invented one: the answer is refused.
  const cited = [...new Set(tokens.map((c) => c.id))];
  const valid = cited.filter((id) => id !== null && byId.has(id));
  if (!valid.length || valid.length !== cited.length || hasStrayChunkRef(text)) {
    return { answer: NO_ANSWER, noAnswer: true, reason: 'answer cited no chunk, or a chunk not in the context', citations: [] };
  }
  // The system prompt asks for a citation after every sentence; hold the model to it.
  if (uncitedSentences(text)) {
    return { answer: NO_ANSWER, noAnswer: true, reason: 'a sentence in the answer has no citation', citations: [] };
  }
  return {
    answer: text.trim(), noAnswer: false,
    citations: valid.map((id) => ({ chunkId: byId.get(id).chunkId, documentId: byId.get(id).documentId, title: byId.get(id).title })),
  };
}
