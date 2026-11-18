import pg from 'pg';
import { config } from './config.js';

// One pool per login role. Requests only ever use appPool; ingest and migrations run as
// separate processes, and in production the API is deployed with DATABASE_URL only.
export const appPool = new pg.Pool({ connectionString: config.databaseUrl, max: 10 });
export const ingestPool = new pg.Pool({ connectionString: config.ingestDatabaseUrl, max: 2 });
export const adminPool = new pg.Pool({ connectionString: config.adminDatabaseUrl, max: 1 });

// pgvector accepts a vector as the text '[0.1,0.2,...]'.
export const toVector = (values) => `[${values.join(',')}]`;
export const endAll = () => Promise.all([appPool.end(), ingestPool.end(), adminPool.end()]);
