import pg from 'pg';
import { config } from './config.js';

// Three roles, three pools. Requests only ever use appPool.
export const appPool = new pg.Pool({ connectionString: config.databaseUrl, max: 10 });
export const ingestPool = new pg.Pool({ connectionString: config.ingestDatabaseUrl, max: 2 });
export const adminPool = new pg.Pool({ connectionString: config.adminDatabaseUrl, max: 1 });

export const toVector = (values) => `[${values.join(',')}]`;
export const endAll = () => Promise.all([appPool.end(), ingestPool.end(), adminPool.end()]);
