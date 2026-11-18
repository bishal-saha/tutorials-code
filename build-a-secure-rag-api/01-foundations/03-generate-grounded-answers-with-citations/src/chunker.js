// Split Markdown into chunks of whole paragraphs, up to maxWords each.
// - A chunk never ends mid-paragraph, so a numbered step stays with its neighbours.
// - Each chunk starts with its heading path ("Title > Section"), so a chunk that says
//   "restart the worker" still says which procedure it belongs to.
// - The last paragraph(s) of a chunk, up to overlapWords, are repeated at the start of the
//   next one, so an answer that straddles the boundary appears whole in at least one chunk.
// - A single paragraph longer than maxWords is split at sentence boundaries.
const words = (s) => s.split(/\s+/).filter(Boolean).length;

function splitLongParagraph(paragraph, maxWords) {
  // Split after . ! or ? that follows a letter or closing bracket, so list markers like "3." stay put.
  const sentences = paragraph.split(/(?<=[A-Za-z)"'][.!?])\s+/).map((s) => `${s} `);
  const parts = [];
  let current = '';
  for (const sentence of sentences) {
    if (current && words(current + sentence) > maxWords) {
      parts.push(current.trim());
      current = '';
    }
    current += sentence;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

export function chunkMarkdown(title, markdown, { maxWords = 120, overlapWords = 25 } = {}) {
  const sections = [];
  let heading = null;
  let paragraphs = [];
  const flush = () => {
    if (paragraphs.length) sections.push({ path: heading ? `${title} > ${heading}` : title, paragraphs });
    paragraphs = [];
  };
  for (const block of markdown.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean)) {
    const h = block.match(/^(#{1,6})\s+(.*)$/);
    if (h && !block.includes('\n')) {
      if (h[1].length === 1) continue; // the document's own title is already in the path
      flush();
      heading = h[2].trim();
    } else {
      paragraphs.push(...(words(block) > maxWords ? splitLongParagraph(block, maxWords) : [block]));
    }
  }
  flush();

  const chunks = [];
  for (const { path, paragraphs: paras } of sections) {
    let current = [];
    const emit = () => {
      chunks.push(`${path}\n\n${current.join('\n\n')}`);
      // carry trailing paragraphs that fit in the overlap budget into the next chunk
      const carry = [];
      for (let i = current.length - 1; i >= 0; i--) {
        if (words([current[i], ...carry].join(' ')) > overlapWords) break;
        carry.unshift(current[i]);
      }
      current = carry.length < current.length ? carry : [];
    };
    for (const p of paras) {
      if (current.length && words([...current, p].join(' ')) > maxWords) {
        emit();
        // never let carried overlap push a chunk past maxWords
        if (current.length && words([...current, p].join(' ')) > maxWords) current = [];
      }
      current.push(p);
    }
    if (current.length) chunks.push(`${path}\n\n${current.join('\n\n')}`);
  }
  return chunks;
}
