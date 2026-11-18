CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL,
  name text NOT NULL
);

CREATE TABLE documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants (id),
  source_key    text NOT NULL,                -- stable id for re-ingest, e.g. the file name
  title         text NOT NULL,
  allowed_roles text[] NOT NULL,              -- the document ACL
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_key),
  UNIQUE (id, tenant_id, allowed_roles),      -- target of the chunks foreign key below
  CHECK (cardinality(allowed_roles) > 0 AND allowed_roles <@ ARRAY['agent', 'end_user'])
);

CREATE TABLE chunks (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id   uuid NOT NULL,
  tenant_id     uuid NOT NULL,
  allowed_roles text[] NOT NULL,
  chunk_index   int NOT NULL,
  content       text NOT NULL,
  embedding     vector(:dimensions) NOT NULL,
  UNIQUE (document_id, chunk_index),
  -- A chunk's tenant and ACL must equal its document's. ON UPDATE CASCADE copies an
  -- ACL change to every chunk; ON DELETE CASCADE removes chunks with their document.
  FOREIGN KEY (document_id, tenant_id, allowed_roles)
    REFERENCES documents (id, tenant_id, allowed_roles) ON UPDATE CASCADE ON DELETE CASCADE
);

-- vector_cosine_ops matches the <=> (cosine distance) operator used by search.
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);

-- ── Lesson 4: roles and row-level security ─────────────────────────────────
-- rag_owner owns the tables and never logs in. rag_app serves requests: it is not the owner
-- and has no BYPASSRLS, so every policy applies to it. rag_ingest is the trusted ingest job.
ALTER TABLE tenants   OWNER TO rag_owner;
ALTER TABLE documents OWNER TO rag_owner;
ALTER TABLE chunks    OWNER TO rag_owner;

GRANT SELECT ON documents, chunks TO rag_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, documents, chunks TO rag_ingest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO rag_ingest;

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;   -- even the owner is filtered
ALTER TABLE chunks    FORCE ROW LEVEL SECURITY;

-- The principal arrives as transaction-local settings (see src/tenant-session.js).
-- NULLIF turns an empty setting into NULL: a pooled connection whose last transaction set
-- the value reads back '' afterwards, and '' would fail the uuid cast. NULL matches no row.
CREATE POLICY principal_can_read ON documents FOR SELECT TO rag_app USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  AND allowed_roles && string_to_array(NULLIF(current_setting('app.roles', true), ''), ',')
);
CREATE POLICY principal_can_read ON chunks FOR SELECT TO rag_app USING (
  tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  AND allowed_roles && string_to_array(NULLIF(current_setting('app.roles', true), ''), ',')
);
