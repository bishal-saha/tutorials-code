import { appPool } from './db.js';

/**
 * Run fn inside one transaction whose session settings carry the principal.
 * set_config(..., true) is transaction-local: the settings vanish at COMMIT or ROLLBACK,
 * so the pooled connection can't carry this principal into the next request.
 */
export async function withPrincipal(principal, fn, pool = appPool) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query("SELECT set_config('app.tenant_id', $1, true), set_config('app.roles', $2, true)",
      [principal.tenantId, principal.roles.join(',')]);
    // A filtered HNSW query can return fewer than k rows; let pgvector keep scanning.
    // relaxed_order finds more matches than strict_order; searchByVector re-sorts them.
    await client.query("SET LOCAL hnsw.iterative_scan = 'relaxed_order'");
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}
