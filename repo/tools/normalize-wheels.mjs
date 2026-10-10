// Normalize an unpacked wheel tree: expand PEP 427 "<dist>.data/{platlib,purelib,scripts,...}"
// directories into their proper locations. Our pip-install.mjs extracts wheels verbatim, so
// these ".data" dirs must be flattened before the packages are importable.
// Usage: node normalize-wheels.mjs <targetDir>
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync, copyFileSync } from 'node:fs';
import { join, basename } from 'node:path';

const targetDir = process.argv[2];
if (!targetDir) {
  console.error('usage: node normalize-wheels.mjs <targetDir>');
  process.exit(2);
}

// Subdirs inside "<dist>.data/" that map onto the purelib/platlib root.
const MERGE_INTO_ROOT = new Set(['purelib', 'platlib']);

function moveInto(srcDir, dstDir) {
  mkdirSync(dstDir, { recursive: true });
  for (const entry of readdirSync(srcDir)) {
    const from = join(srcDir, entry);
    const to = join(dstDir, entry);
    if (existsSync(to)) {
      // Directory collision: recurse so both trees merge instead of clobbering.
      if (statSync(from).isDirectory() && statSync(to).isDirectory()) {
        moveInto(from, to);
        rmSync(from, { recursive: true, force: true });
        continue;
      }
      console.log(`  keep existing ${to} (skip ${from})`);
      continue;
    }
    try {
      renameSync(from, to);
    } catch {
      copyFileSync(from, to);
      rmSync(from, { recursive: true, force: true });
    }
  }
}

let moved = 0;
for (const entry of readdirSync(targetDir)) {
  if (!entry.endsWith('.data')) continue;
  const dataDir = join(targetDir, entry);
  if (!statSync(dataDir).isDirectory()) continue;
  console.log(`expanding ${entry}`);
  for (const sub of readdirSync(dataDir)) {
    const src = join(dataDir, sub);
    if (!statSync(src).isDirectory()) continue;
    if (MERGE_INTO_ROOT.has(sub)) {
      moveInto(src, targetDir);
      rmSync(src, { recursive: true, force: true });
      moved++;
    } else {
      // scripts/, headers/, data/ etc. keep their own folder at the root.
      const dst = join(targetDir, sub);
      if (!existsSync(dst)) {
        renameSync(src, dst);
        moved++;
      }
    }
  }
  // Remove the now-empty .data dir (or leave it if something unexpected remains).
  const rest = readdirSync(dataDir);
  if (rest.length === 0) rmSync(dataDir, { recursive: true, force: true });
  else console.log(`  note: ${entry} still contains ${rest.join(', ')}`);
}

console.log(`normalize: expanded ${moved} wheel .data subdirectories in ${targetDir}`);
