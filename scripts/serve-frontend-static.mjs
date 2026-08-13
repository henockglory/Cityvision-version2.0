#!/usr/bin/env node
/**
 * Low-memory product UI server (replaces Vite HMR on :5174).
 * Serves frontend/dist + proxies /api /health /ai-engine /rules-engine /frigate /go2rtc.
 * Node builtins only — no Vite process, far less OOM risk under WSL RAM pressure.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from 'node:stream';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'frontend', 'dist');
const PORT = Number(process.env.CITEVISION_UI_PORT || 5174);
const HOST = process.env.CITEVISION_UI_HOST || '0.0.0.0';

const PROXIES = [
  { prefix: '/api', target: process.env.CITEVISION_API_URL || 'http://127.0.0.1:8081' },
  { prefix: '/health', target: process.env.CITEVISION_API_URL || 'http://127.0.0.1:8081' },
  { prefix: '/go2rtc', target: process.env.CITEVISION_GO2RTC_URL || 'http://127.0.0.1:1984', strip: '/go2rtc' },
  { prefix: '/ai-engine', target: process.env.CITEVISION_AI_URL || 'http://127.0.0.1:8001', strip: '/ai-engine' },
  {
    prefix: '/rules-engine',
    target: process.env.CITEVISION_RULES_URL || 'http://127.0.0.1:8010',
    strip: '/rules-engine',
  },
  {
    prefix: '/frigate-go2rtc',
    target: process.env.CITEVISION_FRIGATE_URL || 'http://127.0.0.1:5000',
    rewrite: (p) => p.replace(/^\/frigate-go2rtc/, '/api/go2rtc'),
  },
  {
    prefix: '/frigate',
    target: process.env.CITEVISION_FRIGATE_URL || 'http://127.0.0.1:5000',
    strip: '/frigate',
  },
];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.map': 'application/json',
  '.ico': 'image/x-icon',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
};

function matchProxy(urlPath) {
  for (const p of PROXIES) {
    if (urlPath === p.prefix || urlPath.startsWith(p.prefix + '/') || urlPath.startsWith(p.prefix + '?')) {
      return p;
    }
  }
  return null;
}

function rewritePath(urlPath, rule) {
  if (typeof rule.rewrite === 'function') return rule.rewrite(urlPath);
  if (rule.strip) {
    const rest = urlPath.slice(rule.strip.length) || '/';
    return rest.startsWith('/') ? rest : `/${rest}`;
  }
  return urlPath;
}

function proxyRequest(clientReq, clientRes, rule) {
  const incoming = new URL(clientReq.url || '/', `http://${clientReq.headers.host || '127.0.0.1'}`);
  const targetBase = new URL(rule.target);
  const destPath = rewritePath(incoming.pathname + incoming.search, rule);
  const opts = {
    protocol: targetBase.protocol,
    hostname: targetBase.hostname,
    port: targetBase.port || (targetBase.protocol === 'https:' ? 443 : 80),
    path: destPath,
    method: clientReq.method,
    headers: { ...clientReq.headers, host: targetBase.host },
  };
  delete opts.headers['accept-encoding'];

  const upstream = http.request(opts, (upRes) => {
    clientRes.writeHead(upRes.statusCode || 502, upRes.headers);
    pipeline(upRes, clientRes, () => {});
  });
  upstream.on('error', (err) => {
    if (!clientRes.headersSent) {
      clientRes.writeHead(502, { 'content-type': 'application/json' });
    }
    clientRes.end(JSON.stringify({ error: 'proxy_error', message: String(err.message || err) }));
  });
  pipeline(clientReq, upstream, () => {});
}

function safeJoin(root, reqPath) {
  const decoded = decodeURIComponent(reqPath.split('?')[0]);
  const cleaned = path.normalize(decoded).replace(/^(\.\.(\/|\\|$))+/, '');
  const full = path.join(root, cleaned);
  if (!full.startsWith(root)) return null;
  return full;
}

function sendFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, { 'content-type': MIME[ext] || 'application/octet-stream' });
  pipeline(fs.createReadStream(filePath), res, () => {});
}

function serveStatic(req, res) {
  const urlPath = (req.url || '/').split('?')[0];
  let filePath = safeJoin(DIST, urlPath === '/' ? '/index.html' : urlPath);
  if (!filePath) {
    res.writeHead(403).end('Forbidden');
    return;
  }
  if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
    sendFile(res, filePath);
    return;
  }
  // SPA fallback
  const index = path.join(DIST, 'index.html');
  if (fs.existsSync(index)) {
    sendFile(res, index);
    return;
  }
  res.writeHead(404, { 'content-type': 'text/plain' }).end('frontend/dist missing — run npm run build');
}

if (!fs.existsSync(path.join(DIST, 'index.html'))) {
  console.error(`[FAIL] missing ${path.join(DIST, 'index.html')} — build frontend first`);
  process.exit(1);
}

const server = http.createServer((req, res) => {
  const urlPath = (req.url || '/').split('?')[0];
  const rule = matchProxy(urlPath);
  if (rule) {
    proxyRequest(req, res, rule);
    return;
  }
  serveStatic(req, res);
});

server.listen(PORT, HOST, () => {
  console.log(`[OK] citevision static UI http://${HOST}:${PORT} (dist=${DIST})`);
});
