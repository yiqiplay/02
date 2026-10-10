// Robust downloader for large binaries with progress reporting and stall detection.
// Usage: node download.mjs <url> <outFile> [--expect-bytes N] [--stall-ms N]
// Prints throughput so a stalled mirror is obvious instead of silently hanging.
import { createWriteStream, existsSync, mkdirSync, renameSync, statSync, rmSync } from 'node:fs';
import { dirname } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const args = process.argv.slice(2);
const positional = args.filter((a) => !a.startsWith('--'));
const [url, out] = positional;
if (!url || !out) {
  console.error('usage: node download.mjs <url> <outFile> [--expect-bytes N] [--stall-ms N]');
  process.exit(2);
}
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? Number(args[i + 1]) : dflt;
};
const expectBytes = opt('--expect-bytes', 0);
const stallMs = opt('--stall-ms', 45000);

mkdirSync(dirname(out), { recursive: true });
if (existsSync(out)) {
  const size = statSync(out).size;
  if (!expectBytes || size === expectBytes) {
    console.log(`SKIP already present (${size} bytes) ${out}`);
    process.exit(0);
  }
  rmSync(out, { force: true });
}
const tmp = `${out}.part`;
rmSync(tmp, { force: true });

const ac = new AbortController();
let lastBytes = 0;
let lastProgress = Date.now();
let started = Date.now();
let seen = 0;

const watchdog = setInterval(() => {
  const idle = Date.now() - lastProgress;
  if (idle > stallMs) {
    console.error(`STALL: no data for ${Math.round(idle / 1000)}s at ${seen} bytes -> aborting`);
    ac.abort();
  } else if (seen !== lastBytes) {
    const kbs = Math.round(seen / 1024 / Math.max(1, (Date.now() - started) / 1000));
    console.log(`  ... ${(seen / 1048576).toFixed(1)} MiB (${kbs} KiB/s avg)`);
    lastBytes = seen;
  }
}, 10000);

try {
  const res = await fetch(url, { signal: ac.signal, redirect: 'follow' });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  const total = Number(res.headers.get('content-length') || 0);
  console.log(`GET ${url}\n  content-length=${total || 'unknown'}`);
  const body = Readable.fromWeb(res.body);
  body.on('data', (chunk) => {
    seen += chunk.length;
    lastProgress = Date.now();
  });
  await pipeline(body, createWriteStream(tmp));
  clearInterval(watchdog);
  const size = statSync(tmp).size;
  if (!size) throw new Error('downloaded 0 bytes');
  if (expectBytes && size !== expectBytes) throw new Error(`size mismatch: got ${size}, expected ${expectBytes}`);
  renameSync(tmp, out);
  const secs = Math.max(1, (Date.now() - started) / 1000);
  console.log(`OK ${size} bytes -> ${out} (${(size / 1048576 / secs).toFixed(2)} MiB/s)`);
  process.exit(0);
} catch (e) {
  clearInterval(watchdog);
  rmSync(tmp, { force: true });
  console.error(`FAILED ${url}: ${e.name}: ${e.message}`);
  process.exit(1);
}
