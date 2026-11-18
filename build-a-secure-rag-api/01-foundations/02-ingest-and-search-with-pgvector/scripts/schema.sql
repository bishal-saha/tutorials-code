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
