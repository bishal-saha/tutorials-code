// A deterministic stand-in for a model, for tests and offline runs. It follows the prompt's
// rules mechanically: it picks the context sentences that share the most words with the
// question and cites the chunk each came from. It cannot reason, paraphrase or be misled,
// which is exactly why tests use it: the answer path, not the model, is under test.
import { tokenize } from '../embeddings/fake.js';

export function createFakeLlm() {
  return {
    async generate({ user }) {
      const question = user.match(/<question>\n([\s\S]*?)\n<\/question>/)?.[1] ?? '';
      const chunks = [...user.matchAll(/<chunk id="(\d+)">\n([\s\S]*?)\n<\/chunk>/g)].map((m) => ({ id: m[1], text: m[2] }));
      const q = new Set(tokenize(question));
      const scored = [];
      for (const { id, text } of chunks) {
        const body = text.split('\n').slice(1).join('\n'); // skip the heading path line
        for (const sentence of body.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter((s) => s.length > 20)) {
          const overlap = tokenize(sentence).filter((w) => q.has(w)).length;
          if (overlap >= 2) scored.push({ id, sentence, overlap });
        }
      }
      if (!scored.length) return { text: 'NO_ANSWER' };
      scored.sort((a, b) => b.overlap - a.overlap);
      return { text: scored.slice(0, 2).map((s) => `${s.sentence} [chunk:${s.id}]`).join(' ') };
    },
  };
}
