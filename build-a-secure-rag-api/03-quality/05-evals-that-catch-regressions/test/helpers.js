import { SignJWT } from 'jose';
import { adminPool, ingestPool } from '../src/db.js';
import { migrate } from '../scripts/migrate.js';
import { ingestAll } from '../scripts/ingest.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { config } from '../src/config.js';

export const embedder = createEmbeddingProvider({ provider: 'fake', dimensions: 256 });
export const TEST_SECRET = new TextEncoder().encode('test-secret-at-least-32-bytes-long!!');

export async function setup() {
  await migrate();
  await ingestAll(undefined, embedder);
  const { rows } = await ingestPool.query('SELECT slug, id FROM tenants');
  return Object.fromEntries(rows.map((r) => [r.slug, r.id]));
}

export const principal = (tenantId, roles) => ({ userId: 'u-test', tenantId, roles });

export const token = (claims, secret = TEST_SECRET) =>
  new SignJWT(claims).setProtectedHeader({ alg: 'HS256' }).setIssuer(config.jwt.issuer)
    .setAudience(config.jwt.audience).setSubject('u-test').setIssuedAt().setExpirationTime('5m').sign(secret);

/** Chunk ids of one document, looked up as the superuser (bypasses RLS). */
export async function chunkIdsOf(tenantSlug, sourceKey) {
  const { rows } = await adminPool.query(
    `SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id JOIN tenants t ON t.id = d.tenant_id
     WHERE t.slug = $1 AND d.source_key = $2`, [tenantSlug, sourceKey]);
  return new Set(rows.map((r) => Number(r.id)));
}
