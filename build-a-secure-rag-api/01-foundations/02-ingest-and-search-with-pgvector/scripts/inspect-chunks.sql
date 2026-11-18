-- One row per document: chunks vs distinct heading paths (sections), the largest and
-- smallest chunk in words (heading path excluded), and chunks that start mid-list.
SELECT d.title,
       count(*) AS chunks,
       count(DISTINCT split_part(c.content, E'\n', 1)) AS sections,
       max(b.words) AS max_words,
       min(b.words) AS min_words,
       count(*) FILTER (WHERE b.body ~ '^[2-9]\. ') AS starts_mid_list
FROM chunks c
JOIN documents d ON d.id = c.document_id,
LATERAL (SELECT substr(c.content, strpos(c.content, E'\n\n') + 2) AS body) s,
LATERAL (SELECT s.body, cardinality(regexp_split_to_array(trim(s.body), '\s+')) AS words) b
GROUP BY d.title
ORDER BY d.title;
