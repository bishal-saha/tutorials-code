// A sketch of a real adapter for a chat endpoint that accepts { model, messages } and returns
// { choices: [{ message: { content } }] }. Adapt it to your provider's API.
// Not exercised by the tests, which use the fake model.
export function createHttpLlm({ url, model, apiKey }) {
  if (!url || !model) throw new Error('LLM_URL and LLM_MODEL are required for the http provider');
  return {
    async generate({ system, user }) {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) },
        body: JSON.stringify({ model, messages: [{ role: 'system', content: system }, { role: 'user', content: user }], temperature: 0 }),
      });
      if (!res.ok) throw new Error(`Model request failed: ${res.status}`);
      const body = await res.json();
      return { text: body.choices[0].message.content };
    },
  };
}
