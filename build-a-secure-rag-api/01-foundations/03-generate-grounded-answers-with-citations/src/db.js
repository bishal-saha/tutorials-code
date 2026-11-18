import pg from 'pg';
import { config } from './config.js';

export const pool = new pg.Pool({ connectionString: config.databaseUrl, max: 10 });

// pgvector accepts a vector as the text '[0.1,0.2,...]'.
export const toVector = (values) => `[${values.join(',')}]`;
