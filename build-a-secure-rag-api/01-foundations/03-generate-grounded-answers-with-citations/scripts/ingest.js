// The trusted ingest job: one folder per tenant, each with a manifest that the tenant's
// admin controls. The tenant comes from the folder the job was pointed at, never from
// anything inside a document.
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pool } from '../src/db.js';
import { createEmbeddingProvider } from '../src/embeddings/provider.js';
import { ingestDocument } from '../src/ingest.js';

export async function ingestAll(root = new URL('../data/tenants/', import.meta.url).pathname, provider = createEmbeddingProvider()) {
  const summary = [];
  for (const slug of (await readdir(root)).sort()) {
    const manifest = JSON.parse(await readFile(join(root, slug, 'manifest.json'), 'utf8'));
    const { rows: [tenant] } = await pool.query(
      `INSERT INTO tenants (slug, name) VALUES ($1, $2)
       ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id`,
      [slug, manifest.name],
    );
    for (const doc of manifest.documents) {
      const markdown = await readFile(join(root, slug, doc.file), 'utf8');
      const result = await ingestDocument(provider, {
        tenantId: tenant.id, sourceKey: doc.file, title: doc.title, allowedRoles: doc.allowedRoles, markdown,
      });
      summary.push({ tenant: slug, file: doc.file, roles: doc.allowedRoles.join(','), chunks: result.chunks });
    }
  }
  return summary;
}

if (import.meta.main) {
  console.table(await ingestAll());
  await pool.end();
}
