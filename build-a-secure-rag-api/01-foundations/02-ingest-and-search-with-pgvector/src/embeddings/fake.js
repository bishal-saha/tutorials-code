// A deterministic, offline embedder for tests and local runs. It hashes words into a
// fixed-length vector, so texts that share words land close together. It knows nothing
// about meaning: "reset password" and "recover account access" won't match. A real
// embedding model is what gives you that.
const STOPWORDS = new Set('a an and are as at be by can do for from how i if in is it my of on or our the to we what when with you your'.split(' '));

const fnv1a = (s) => {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
};

export const tokenize = (text) =>
  text.toLowerCase().replace(/[^a-z0-9\s-]/g, ' ').split(/\s+/)
    .filter((w) => w.length > 1 && !STOPWORDS.has(w))
    .map((w) => w.replace(/(ing|ed|es|s)$/, ''));

export function createFakeEmbedder(dimensions = 256) {
  const embedOne = (text) => {
    const v = new Array(dimensions).fill(0);
    for (const token of tokenize(text)) {
      const h = fnv1a(token);
      v[h % dimensions] += (h & 0x80000000) ? -1 : 1;
    }
    const norm = Math.hypot(...v) || 1;
    return v.map((x) => x / norm);
  };
  return { dimensions, embed: async (texts) => texts.map(embedOne) };
}
