// Parallel chunked downloader: splits a file into byte ranges fetched concurrently,
// then merges the parts. Falls back to a single stream when the server ignores Range.
// Usage: node pget.mjs <url> <outFile> [--conns N] [--expect-bytes N] [--proxy-prefix URL]
import { createWriteStream, existsSync, mkdirSync, renameSync, rmSync, statSync, openSync, writeSync, closeSync, readSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const args = process.argv.slice(2);
const positional = args.filter((a) => !a.startsWith('--'));
const [rawUrl, out] = positional;
if (!rawUrl || !out) {
  console.error('usage: node pget.mjs <url> <outFile> [--conns N] [--expect-bytes N]');
  process.exit(2);
}
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const CONNS = Math.max(1, Number(opt('--conns', 8)));
const expectBytes = Number(opt('--expect-bytes', 0));
const stallMs = Number(opt('--stall-ms', 60000));

// A GitHub proxy prefix looks like "https://gh-proxy.com/" and is prepended to the real URL.
const proxyPrefix = opt('--proxy-prefix', '');
const url = proxyPrefix ? proxyPrefix.replace(/\/$/, '') + '/' + rawUrl : rawUrl;

mkdirSync(dirname(out), { recursive: true });
if (existsSync(out)) {
  const size = statSync(out).size;
  if (!expectBytes || size === expectBytes) {
    console.log(`SKIP already present (${size} bytes) ${out}`);
    process.exit(0);
  }
  rmSync(out, { force: true });
}
const partDir = `${out}.parts`;
mkdirSync(partDir, { recursive: true });

const t0 = Date.now();

// 1) Probe size + Range support.
let total = 0;
let rangeOk = false;
try {
  const head = await fetch(url, { headers: { Range: 'bytes=0-0' } });
  const cr = head.headers.get('content-range');
  if (cr && /bytes\s+\d+-\d+\/(\d+)/.test(cr)) {
    total = Number(cr.match(/bytes\s+\d+-\d+\/(\d+)/)[1]);
    rangeOk = true;
  } else {
    total = Number(head.headers.get('content-length') || 0);
  }
  if (head.body) await head.body.cancel().catch(() => {});
  console.log(`probe: status=${head.status} total=${total || 'unknown'} range=${rangeOk}`);
} catch (e) {
  console.log(`probe failed (${e.message}); falling back to single stream`);
}

async function fetchRange(start, end, dest) {
  const ac = new AbortController();
  let last = Date.now();
  let got = 0;
  const watchdog = setInterval(() => {
    if (Date.now() - last > stallMs) {
      console.error(`  part ${start}-${end}: stalled at ${got} bytes, aborting`);
      ac.abort();
    }
  }, 10000);
  try {
    const res = await fetch(url, { headers: { Range: `bytes=${start}-${end}` }, signal: ac.signal });
    if (!res.ok && res.status !== 206) throw new Error(`HTTP ${res.status}`);
    const body = Readable.fromWeb(res.body);
    body.on('data', (c) => {
      got += c.length;
      last = Date.now();
    });
    await pipeline(body, createWriteStream(dest));
    const size = statSync(dest).size;
    const want = end - start + 1;
    if (size !== want) throw new Error(`part size ${size} != expected ${want}`);
    return size;
  } finally {
    clearInterval(watchdog);
  }
}

let ok = false;
if (rangeOk && total > 0 && CONNS > 1) {
  const chunk = Math.ceil(total / CONNS);
  const jobs = [];
  for (let i = 0; i < CONNS; i++) {
    const start = i * chunk;
    const end = Math.min(total - 1, start + chunk - 1);
    if (start > end) break;
    jobs.push(fetchRange(start, end, join(partDir, `part${String(i).padStart(3, '0')}`)));
  }
  try {
    const sizes = await Promise.all(jobs);
    const sum = sizes.reduce((a, b) => a + b, 0);
    if (sum !== total) throw new Error(`merged size ${sum} != total ${total}`);
    // Merge parts in order.
    const fd = openSync(out, 'w');
    const buf = Buffer.alloc(4 * 1024 * 1024);
    for (let i = 0; i < jobs.length; i++) {
      const p = join(partDir, `part${String(i).padStart(3, '0')}`);
      const pfd = openSync(p, 'r');
      let pos = 0;
      for (;;) {
        const n = readSync(pfd, buf, 0, buf.length, pos);
        if (n <= 0) break;
        writeSync(fd, buf, 0, n);
        pos += n;
      }
      closeSync(pfd);
    }
    closeSync(fd);
    ok = true;
  } catch (e) {
    console.error(`parallel download failed: ${e.message}; falling back to single stream`);
  }
  rmSync(partDir, { recursive: true, force: true });
}

if (!ok) {
  const tmp = `${out}.single`;
  rmSync(tmp, { force: true });
  const parts = rangeOk && total ? Math.ceil(total / (8 * 1024 * 1024)) : 1;
  const fd = openSync(tmp, 'w');
  const buf = Buffer.alloc(4 * 1024 * 1024);
  for (let i = 0; i < parts; i++) {
    const start = i * 8 * 1024 * 1024;
    const end = rangeOk && total ? Math.min(total - 1, start + 8 * 1024 * 1024 - 1) : undefined;
    const res = await fetch(url, end !== undefined ? { headers: { Range: `bytes=${start}-${end}` } } : {});
    if (!res.ok && res.status !== 206) throw new Error(`HTTP ${res.status}`);
    const body = Readable.fromWeb(res.body);
    for await (const c of body) writeSync(fd, c);
    process.stdout.write(`\r  sequential: ${((i + 1) / parts * 100).toFixed(0)}%   `);
  }
  process.stdout.write('\n');
  closeSync(fd);
  renameSync(tmp, out);
}

const size = statSync(out).size;
if (expectBytes && size !== expectBytes) {
  console.error(`size mismatch: got ${size}, expected ${expectBytes}`);
  process.exit(1);
}
const secs = Math.max(0.1, (Date.now() - t0) / 1000);
console.log(`OK ${size} bytes -> ${out} (${(size / 1048576 / secs).toFixed(2)} MiB/s, ${secs.toFixed(1)}s)`);
