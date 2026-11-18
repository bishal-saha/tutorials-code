// Run as the superuser (DATABASE_URL_ADMIN). Creates the three roles if needed, then
// recreates the schema with ownership, grants and row-level security.
import { readFile } from 'node:fs/promises';
import { adminPool } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';

const ROLES = `
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_owner')  THEN CREATE ROLE rag_owner NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app')    THEN CREATE ROLE rag_app LOGIN PASSWORD 'rag_app' NOBYPASSRLS; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_ingest') THEN CREATE ROLE rag_ingest LOGIN PASSWORD 'rag_ingest' BYPASSRLS; END IF;
END $$;`;

export async function migrate() {
  const { dimensions } = createEmbeddingProvider();
  const ddl = (await readFile(new URL('./schema.sql', import.meta.url), 'utf8')).replace(':dimensions', String(dimensions));
  await adminPool.query(ROLES);
  await adminPool.query('DROP TABLE IF EXISTS chunks, documents, tenants CASCADE');
  await adminPool.query(ddl);
  const { rows } = await adminPool.query(`
    SELECT r.rolname, r.rolbypassrls, r.rolsuper, (SELECT tableowner FROM pg_tables WHERE tablename = 'chunks') AS chunks_owner
    FROM pg_roles r WHERE r.rolname = 'rag_app'`);
  return { dimensions, app: rows[0] };
}

if (import.meta.main) {
  console.log(await migrate());
  await adminPool.end();
}
