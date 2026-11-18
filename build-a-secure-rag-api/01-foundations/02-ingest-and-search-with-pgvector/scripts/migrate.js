// Recreates the schema. The vector length comes from the embedding provider, because the
// column must match whatever the provider returns.
import { readFile } from 'node:fs/promises';
import { pool } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';

export async function migrate() {
  const { dimensions } = createEmbeddingProvider();
  if (!Number.isInteger(dimensions) || dimensions <= 0) throw new Error(`Bad dimensions: ${dimensions}`);
  const ddl = (await readFile(new URL('./schema.sql', import.meta.url), 'utf8')).replace(':dimensions', String(dimensions));
  await pool.query('DROP TABLE IF EXISTS chunks, documents, tenants CASCADE');
  await pool.query(ddl);
  const { rows } = await pool.query("SELECT extversion FROM pg_extension WHERE extname = 'vector'");
  return { dimensions, pgvector: rows[0].extversion };
}

if (import.meta.main) {
  console.log(await migrate());
  await pool.end();
}
