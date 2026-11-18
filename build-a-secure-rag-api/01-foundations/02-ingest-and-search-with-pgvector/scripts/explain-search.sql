-- Plan the exact query src/search.js sends; GENERIC_PLAN keeps its $1/$2 placeholders.
-- The demo table is tiny, so disable sequential scans to see whether the index can serve it.
SET enable_seqscan = off;
EXPLAIN (GENERIC_PLAN, COSTS OFF)
SELECT c.id, c.document_id, d.title, c.chunk_index, c.distance, c.content
FROM (
  SELECT id, document_id, chunk_index, content, embedding <=> $1 AS distance
  FROM chunks
  ORDER BY embedding <=> $1
  LIMIT $2
) c
JOIN documents d ON d.id = c.document_id
ORDER BY c.distance;
