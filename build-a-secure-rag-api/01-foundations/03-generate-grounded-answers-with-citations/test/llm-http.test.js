// No database needed: runs the http adapter against a local stub server.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHttpLlm } from '../src/llm/http.js';

test('the http adapter sends both messages and reads the reply', async () => {
  let received;
  const stub = createServer((req, res) => {
    let raw = '';
    req.on('data', (d) => { raw += d; });
    req.on('end', () => {
      received = { auth: req.headers.authorization, body: JSON.parse(raw) };
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ choices: [{ message: { content: 'Revoke it. [chunk:1]' } }] }));
    });
  });
  await new Promise((r) => stub.listen(0, '127.0.0.1', r));
  const llm = createHttpLlm({ url: `http://127.0.0.1:${stub.address().port}/v1/chat`, model: 'test-model', apiKey: 'k' });
  const { text } = await llm.generate({ system: 'S', user: 'U' });
  stub.close();
  assert.equal(text, 'Revoke it. [chunk:1]');
  assert.equal(received.auth, 'Bearer k');
  assert.deepEqual(received.body.messages, [{ role: 'system', content: 'S' }, { role: 'user', content: 'U' }]);
});
