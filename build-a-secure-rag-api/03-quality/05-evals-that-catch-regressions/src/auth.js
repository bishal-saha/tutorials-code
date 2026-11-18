import { jwtVerify } from 'jose';
import { config } from './config.js';

const ROLES = new Set(['agent', 'end_user']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Verify a bearer token and turn it into a principal. The tenant and roles come only from
 * the verified token, never from the request body or query string.
 * Local development uses a shared HS256 secret; in production pass a key set from your
 * identity provider instead, e.g. createRemoteJWKSet(new URL('https://idp.example/.well-known/jwks.json')).
 */
export async function verifyPrincipal(token, key = new TextEncoder().encode(config.jwt.secret)) {
  const { payload } = await jwtVerify(token, key, {
    issuer: config.jwt.issuer,
    audience: config.jwt.audience,
    // jose checks exp only when the claim is present; require it, so every token expires.
    requiredClaims: ['exp'],
    // One algorithm family per key: a shared secret only ever verifies HS256, and a key set
    // from an identity provider only asymmetric signatures, so a token can't pick the weaker one.
    algorithms: key instanceof Uint8Array ? ['HS256'] : ['RS256', 'ES256'],
  });
  const roles = Array.isArray(payload.roles) ? payload.roles.filter((r) => ROLES.has(r)) : [];
  if (typeof payload.sub !== 'string' || !UUID.test(payload.tenant_id ?? '') || roles.length === 0) {
    throw new Error('token is missing sub, a tenant_id or a known role');
  }
  return { userId: payload.sub, tenantId: payload.tenant_id, roles };
}
