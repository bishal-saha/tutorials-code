import { ingestPool as pool, toVector } from './db.js';
import { chunkMarkdown } from './chunker.js';
import { config } from './config.js';

const ROLES = new Set(['agent', 'end_user']);

/**
 * Ingest (or re-ingest) one document for one tenant.
 * tenantId comes from the caller, which is the trusted ingest job, never from the document.
 * Embedding happens before the transaction, so no database lock is held during a slow call.
 */
export async function ingestDocument(provider, { tenantId, sourceKey, title, allowedRoles, markdown }) {
  if (!allowedRoles.length || !allowedRoles.every((r) => ROLES.has(r))) {
    throw new Error(`Invalid document ACL for ${sourceKey}: ${allowedRoles}`);
  }
  const chunks = chunkMarkdown(title, markdown, config.chunking);
  const vectors = await provider.embed(chunks);

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const { rows: [doc] } = await client.query(
      `INSERT INTO documents (tenant_id, source_key, title, allowed_roles)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (tenant_id, source_key)
       DO UPDATE SET title = EXCLUDED.title, allowed_roles = EXCLUDED.allowed_roles, updated_at = now()
       RETURNING id, allowed_roles`,
      [tenantId, sourceKey, title, allowedRoles],
    );
    // Replace the old chunks in the same transaction: a reader sees the old set or the new one.
    await client.query('DELETE FROM chunks WHERE document_id = $1', [doc.id]);
    for (const [i, content] of chunks.entries()) {
      await client.query(
        `INSERT INTO chunks (document_id, tenant_id, allowed_roles, chunk_index, content, embedding)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [doc.id, tenantId, doc.allowed_roles, i, content, toVector(vectors[i])],
      );
    }
    await client.query('COMMIT');
    return { documentId: doc.id, chunks: chunks.length };
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}
