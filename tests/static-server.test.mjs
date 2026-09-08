import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { createDemoServer } from '../scripts/serve-demo.mjs';

async function start(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return `http://127.0.0.1:${server.address().port}`;
}

test('serves the production UI, bounded audio ranges, and explicit missing-backend errors', async t => {
  const server = createDemoServer({ backend: '' });
  t.after(() => server.close());
  const base = await start(server);
  const html = await fetch(base);
  assert.equal(html.status, 200);
  assert.match(await html.text(), /听间 Tingjian/);
  const audio = await fetch(`${base}/assets/demo-chimes.wav`, { headers: { Range: 'bytes=0-43' } });
  assert.equal(audio.status, 206);
  const wave = Buffer.from(await audio.arrayBuffer());
  assert.equal(wave.length, 44);
  assert.equal(wave.toString('ascii', 0, 4), 'RIFF');
  const invalid = await fetch(`${base}/assets/demo-chimes.wav`, { headers: { Range: 'bytes=99999999-' } });
  assert.equal(invalid.status, 416);
  const missing = await fetch(`${base}/does-not-exist.js`);
  assert.equal(missing.status, 404);
  const api = await fetch(`${base}/api/show`, { method: 'POST', body: '{}' });
  assert.equal(api.status, 503);
  const secret = await fetch(`${base}/%2e%2e%2fapp.py`);
  assert.equal(secret.status, 403);
});

test('forwards both the API and relative voice URLs without forwarding browser cookies', async t => {
  const calls = [];
  const backend = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    calls.push({ url: request.url, headers: request.headers, body: Buffer.concat(chunks).toString() });
    if (request.url.startsWith('/voice/')) response.writeHead(206, { 'Content-Type': 'audio/mpeg', 'Content-Range': 'bytes 0-2/3' }).end('mp3');
    else response.writeHead(200, { 'Content-Type': 'application/json' }).end('{"items":[]}');
  });
  t.after(() => backend.close());
  const server = createDemoServer({ backend: await start(backend) });
  t.after(() => server.close());
  const base = await start(server);
  const api = await fetch(`${base}/api/show`, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: 'test-only=value' }, body: '{"theme":"午后咖啡"}' });
  assert.equal(api.status, 200);
  assert.deepEqual(await api.json(), { items: [] });
  assert.equal(calls[0].body, '{"theme":"午后咖啡"}');
  assert.equal(calls[0].headers.cookie, undefined);
  const voice = await fetch(`${base}/voice/test.mp3`, { headers: { Range: 'bytes=0-2' } });
  assert.equal(voice.status, 206);
  assert.equal(voice.headers.get('content-range'), 'bytes 0-2/3');
  assert.equal(await voice.text(), 'mp3');
  assert.equal(calls[1].headers.range, 'bytes=0-2');
});
