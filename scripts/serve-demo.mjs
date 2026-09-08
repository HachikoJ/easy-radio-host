import http from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../backend/static/', import.meta.url));
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.wav': 'audio/wav', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8' };

export function createDemoServer({ backend = process.env.RADIO_BACKEND_URL } = {}) {
  return http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/voice/')) {
        if (!backend) {
          response.writeHead(503, { 'Content-Type': 'application/json' }).end(JSON.stringify({ detail: 'Demo server has no backend. Use ?demo=1 or configure RADIO_BACKEND_URL.' }));
          return;
        }
        const chunks = [];
        for await (const chunk of request) chunks.push(chunk);
        const headers = {};
        for (const name of ['content-type', 'range']) if (request.headers[name]) headers[name] = request.headers[name];
        const upstream = await fetch(new URL(url.pathname + url.search, backend), {
          method: request.method, headers,
          body: ['GET', 'HEAD'].includes(request.method) ? undefined : Buffer.concat(chunks),
          signal: AbortSignal.timeout(90000)
        });
        const resultHeaders = {};
        for (const name of ['content-type', 'content-range', 'accept-ranges']) if (upstream.headers.has(name)) resultHeaders[name] = upstream.headers.get(name);
        response.writeHead(upstream.status, resultHeaders).end(request.method === 'HEAD' ? undefined : Buffer.from(await upstream.arrayBuffer()));
        return;
      }
      if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
      let pathname;
      try { pathname = decodeURIComponent(url.pathname); } catch { response.writeHead(400).end(); return; }
      const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
      if (!file.startsWith(root)) { response.writeHead(403).end(); return; }
      const info = await stat(file);
      if (!info.isFile()) { response.writeHead(404).end(); return; }
      const headers = { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store', 'Accept-Ranges': 'bytes', 'X-Content-Type-Options': 'nosniff' };
      let start = 0, end = info.size - 1, status = 200;
      if (request.headers.range) {
        const range = request.headers.range.match(/^bytes=(\d*)-(\d*)$/);
        if (!range || (!range[1] && !range[2])) { response.writeHead(416, { 'Content-Range': `bytes */${info.size}` }).end(); return; }
        start = range[1] ? Number(range[1]) : Math.max(0, info.size - Number(range[2]));
        end = range[1] && range[2] ? Math.min(Number(range[2]), info.size - 1) : info.size - 1;
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= info.size) { response.writeHead(416, { 'Content-Range': `bytes */${info.size}` }).end(); return; }
        status = 206; headers['Content-Range'] = `bytes ${start}-${end}/${info.size}`;
      }
      response.writeHead(status, { ...headers, 'Content-Length': end - start + 1 });
      if (request.method === 'HEAD') response.end();
      else createReadStream(file, { start, end }).on('error', () => response.destroy()).pipe(response);
    } catch (error) {
      if (response.headersSent) { response.destroy(); return; }
      response.writeHead(error.code === 'ENOENT' ? 404 : 502, { 'Content-Type': 'application/json' }).end(JSON.stringify({ detail: 'Resource unavailable.' }));
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PREVIEW_PORT || 8131);
  createDemoServer().listen(port, '127.0.0.1', () => console.log(`Tingjian: http://127.0.0.1:${port}/?demo=1`));
}
