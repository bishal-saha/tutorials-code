// A sketch of a real adapter for an embeddings endpoint with this request and response shape:
// POST { model, input: string[] } -> { data: [{ embedding: number[] }] }.
// Not exercised by the tests, which use the fake embedder.
export function createHttpEmbedder({ url, model, apiKey, dimensions }) {
  if (!url || !model) throw new Error('EMBEDDINGS_URL and EMBEDDINGS_MODEL are required for the http provider');
  return {
    dimensions,
    async embed(texts) {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) },
        body: JSON.stringify({ model, input: texts }),
      });
      if (!res.ok) throw new Error(`Embedding request failed: ${res.status}`);
      const { data } = await res.json();
      const vectors = data.map((d) => d.embedding);
      if (vectors.some((v) => v.length !== dimensions)) throw new Error(`Provider returned vectors that are not ${dimensions}-dimensional`);
      return vectors;
    },
  };
}
