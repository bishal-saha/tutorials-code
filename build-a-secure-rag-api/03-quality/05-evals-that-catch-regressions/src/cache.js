import { createHash } from 'node:crypto';

/**
 * If you cache retrieval results or answers, key them by everything that changes what the
 * caller may see: tenant, roles (order-independent), the normalised question, and an index
 * version you bump on every ingest, so a deleted or re-permissioned document can't be served
 * from cache. The series doesn't add a cache; this is the rule any cache must follow.
 */
export function cacheKey(principal, question, indexVersion) {
  const roles = [...principal.roles].sort();
  const normalised = question.trim().toLowerCase().replace(/\s+/g, ' ');
  return createHash('sha256').update(JSON.stringify([principal.tenantId, roles, normalised, indexVersion])).digest('hex');
}
