// Install a Python package from PyPI into a target dir without pip's temp-dir dance.
// Usage: node pip-install.mjs <targetDir> <pkg> [<pkg>...]
// Resolves the best matching wheel for the running CPython (ABI3/cpXY/none) on win_amd64,
// downloads it with fetch(), then extracts it with Node's own zip handling via a spawned Python.
import { createWriteStream, existsSync, mkdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { execFileSync } from 'node:child_process';

const [targetDir, ...pkgs] = process.argv.slice(2);
if (!targetDir || pkgs.length === 0) {
  console.error('usage: node pip-install.mjs <targetDir> <pkg> [pkg...]');
  process.exit(2);
}

const PY = process.env.PIP_PYTHON || 'python';
const PY_TAG = process.env.PIP_PY_TAG || 'cp312';
const DL_DIR = process.env.PIP_DL_DIR || join(targetDir, '..', 'wheels');
const PLAT = 'win_amd64';

mkdirSync(targetDir, { recursive: true });
mkdirSync(DL_DIR, { recursive: true });

// Rank wheel filenames: prefer exact cpXY, then abi3, then py3-none-any.
function scoreWheel(name, pyTag) {
  const n = name.toLowerCase();
  if (!n.endsWith('.whl')) return -1;
  if (!n.includes(PLAT) && !n.includes('none-any')) return -1;
  let s = 0;
  if (n.includes(`-${pyTag}-`)) s += 100;
  else if (n.includes('-abi3-')) s += 80;
  else if (n.includes('-py3-')) s += 60;
  else if (n.includes('-py2.py3-')) s += 55;
  else return -1;
  // Prefer newer python tags when a package ships several abi3 wheels.
  const m = n.match(/-(cp3\d+)-abi3-/);
  if (m) {
    const v = Number(m[1].slice(2));
    const want = Number(pyTag.slice(2));
    if (v > want) return -1; // built for a newer interpreter than ours
    s += v / 1000;
  }
  return s;
}

async function fetchJson(url) {
  const res = await fetch(url, { redirect: 'follow', headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

async function download(url, out) {
  if (existsSync(out) && statSync(out).size > 0) {
    console.log(`  cached ${out}`);
    return out;
  }
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`HTTP ${res.status} downloading ${url}`);
  mkdirSync(dirname(out), { recursive: true });
  const tmp = `${out}.part`;
  await pipeline(Readable.fromWeb(res.body), createWriteStream(tmp));
  const size = statSync(tmp).size;
  if (!size) throw new Error(`empty download ${url}`);
  const { renameSync } = await import('node:fs');
  renameSync(tmp, out);
  return out;
}

const wheels = [];
for (const spec of pkgs) {
  // Support "name==version" pins.
  const [name, ver] = spec.split('==');
  console.log(`resolving ${spec} ...`);
  const meta = await fetchJson(`https://pypi.org/pypi/${encodeURIComponent(name)}/json`);
  let files;
  if (ver) {
    const rel = meta.releases?.[ver];
    if (!rel) throw new Error(`version ${ver} not found for ${name}`);
    files = rel;
  } else {
    files = meta.urls;
  }
  const candidates = (files || [])
    .filter((f) => f.packagetype === 'bdist_wheel' || (f.filename || '').endsWith('.whl'))
    .map((f) => ({ ...f, score: scoreWheel(f.filename, PY_TAG) }))
    .filter((f) => f.score > 0)
    .sort((a, b) => b.score - a.score);
  if (candidates.length === 0) {
    throw new Error(`no compatible wheel for ${spec} (pyTag=${PY_TAG}, plat=${PLAT})`);
  }
  const best = candidates[0];
  console.log(`  -> ${best.filename} (${best.size} bytes)`);
  const out = join(DL_DIR, best.filename);
  await download(best.url, out);
  wheels.push({ path: resolve(out), filename: best.filename, name, version: ver || meta.info.version });
}

// Extract every wheel into targetDir using Python's zipfile (no pip temp dirs involved).
const extractScript = join(DL_DIR, '_extract.py');
writeFileSync(
  extractScript,
  [
    'import sys, zipfile, os',
    'target = sys.argv[1]',
    'for w in sys.argv[2:]:',
    '    with zipfile.ZipFile(w) as z:',
    '        names = z.namelist()',
    '        z.extractall(target)',
    '    print("  extracted", os.path.basename(w), len(names), "entries")',
  ].join('\n'),
  'utf8'
);

const args = [extractScript, targetDir, ...wheels.map((w) => w.path)];
console.log('extracting into', targetDir);
// NOTE: stdio must NOT be 'pipe' — confined DSH sandboxes cannot create the named
// pipes that piped stdio needs (EPERM), so inherit the parent's handles instead.
execFileSync(PY, args, { stdio: 'inherit' });

console.log('\nINSTALLED:');
for (const w of wheels) console.log(`  ${w.name}==${w.version}  (${w.filename})`);
