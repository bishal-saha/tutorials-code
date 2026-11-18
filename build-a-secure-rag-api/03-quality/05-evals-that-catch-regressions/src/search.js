import { toVector } from './db.js';
import { withPrincipal } from './tenant-session.js';

/**
 * Top-k chunks the principal may see, by cosine distance. Run it through withPrincipal:
 * the explicit WHERE states the intent, and row-level security enforces the same rule if a
 * future query forgets it. The filter is inside the query, so ranking only ever sees
 * visible rows and no foreign chunk reaches this process.
 */
export async function searchChunks(client, embedder, principal, query, k = 5) {
  const [vector] = await embedder.embed([query]);
  return searchByVector(client, vector, principal, k);
}

/** The query itself, for a vector embedded before the transaction opened. */
export async function searchByVector(client, vector, principal, k = 5) {
  const { rows } = await client.query(
    `WITH nearest AS MATERIALIZED (
       SELECT id, document_id, chunk_index, content, embedding <=> $1 AS distance
       FROM chunks
       WHERE tenant_id = $2 AND allowed_roles && $3
       ORDER BY distance
       LIMIT $4
     )
     SELECT n.id, n.document_id, d.title, n.chunk_index, n.distance, n.content
     FROM nearest n
     JOIN documents d ON d.id = n.document_id
     ORDER BY n.distance + 0  -- re-sort: relaxed_order may return rows slightly out of order`,
    [toVector(vector), principal.tenantId, principal.roles, k],
  );
  return rows.map((r) => ({
    chunkId: Number(r.id), documentId: r.document_id, title: r.title, chunkIndex: r.chunk_index,
    distance: Number(Number(r.distance).toFixed(4)), content: r.content,
  }));
}

/**
 * What the API calls. The embedding, usually a network call to a provider, happens before the
 * transaction opens, so no pooled connection sits idle in a transaction while it waits.
 */
export async function retrieve(embedder, principal, query, k = 5) {
  const [vector] = await embedder.embed([query]);
  return withPrincipal(principal, (client) => searchByVector(client, vector, principal, k));
}
