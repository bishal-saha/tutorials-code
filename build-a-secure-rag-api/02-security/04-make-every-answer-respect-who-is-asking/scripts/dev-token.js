// Mints a short-lived local development token for a tenant and roles, signed with JWT_SECRET.
// Local use only: in production your identity provider issues tokens.
//   node --env-file=.env scripts/dev-token.js acme end_user
import { SignJWT } from 'jose';
import { config } from '../src/config.js';
import { ingestPool } from '../src/db.js';

const [slug, ...roles] = process.argv.slice(2);
if (!slug || !roles.length) throw new Error('usage: dev-token.js <tenant-slug> <role> [role...]');
const { rows } = await ingestPool.query('SELECT id FROM tenants WHERE slug = $1', [slug]);
await ingestPool.end();
if (!rows.length) throw new Error(`no tenant ${slug}`);
console.log(await new SignJWT({ tenant_id: rows[0].id, roles })
  .setProtectedHeader({ alg: 'HS256' }).setIssuer(config.jwt.issuer).setAudience(config.jwt.audience)
  .setSubject(`dev-${slug}-${roles.join('-')}`).setIssuedAt().setExpirationTime('1h')
  .sign(new TextEncoder().encode(config.jwt.secret)));
