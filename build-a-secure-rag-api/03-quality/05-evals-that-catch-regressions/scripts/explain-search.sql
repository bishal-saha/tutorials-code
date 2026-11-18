-- Plan the exact filtered query src/search.js sends (searchByVector); GENERIC_PLAN keeps
-- the $1..$4 placeholders. On the 21 fixture chunks the planner picks a sequential scan
-- and a sort: exact search, so the golden run never exercises the HNSW index.
EXPLAIN (GENERIC_PLAN, COSTS OFF)
WITH nearest AS MATERIALIZED (
  SELECT id, document_id, chunk_index, content, embedding <=> $1::vector AS distance
  FROM chunks
  WHERE tenant_id = $2::uuid AND allowed_roles && $3::text[]
  ORDER BY distance
  LIMIT $4::int
)
SELECT n.id, n.document_id, d.title, n.chunk_index, n.distance, n.content
FROM nearest n
JOIN documents d ON d.id = n.document_id
ORDER BY n.distance + 0;
