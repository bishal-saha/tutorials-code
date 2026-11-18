import { pool, toVector } from './db.js';

/**
 * Top-k chunks by cosine distance (<=>; smaller is closer).
 *
 * UNPROTECTED: this searches every tenant's chunks. It exists to show the ranking on its
 * own; lesson 4 adds the tenant and role filter inside this query, plus row-level security.
 * Never deploy it as is.
 */
export async function searchChunks(provider, query, k = 5) {
  const [vector] = await provider.embed([query]);
  const { rows } = await pool.query(
    `SELECT c.id, c.document_id, d.title, c.chunk_index, c.distance, c.content
     FROM (
       SELECT id, document_id, chunk_index, content, embedding <=> $1 AS distance
       FROM chunks
       ORDER BY embedding <=> $1
       LIMIT $2
     ) c
     JOIN documents d ON d.id = c.document_id
     ORDER BY c.distance`,
    [toVector(vector), k],
  );
  return rows.map((r) => ({
    chunkId: Number(r.id),
    documentId: r.document_id,
    title: r.title,
    chunkIndex: r.chunk_index,
    distance: Number(Number(r.distance).toFixed(4)),
    content: r.content,
  }));
}
