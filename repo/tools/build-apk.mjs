// Build + sign the Android APK without Gradle.
// Pipeline: aapt2 compile -> aapt2 link -> javac -> d8 -> zip -> zipalign -> apksigner
//
// Deliberately avoids Gradle/AGP and AndroidX: the app uses only platform APIs, so the
// whole build needs nothing from the network and stays reproducible on this machine.
//
// Usage: node build-apk.mjs [--version-name 1.0.0] [--version-code 1] [--debug]
import { execFileSync, execSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync, copyFileSync, readFileSync } from 'node:fs';
import { join, resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJ = resolve(HERE, '..');
const ANDROID = join(PROJ, 'android', 'app');
const WS = resolve(PROJ, '..');

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
};
const VERSION_NAME = arg('--version-name', '1.0.0');
const VERSION_CODE = arg('--version-code', '1');

// ---------------------------------------------------------------- toolchain
const SDK = process.env.ANDROID_SDK_ROOT || join(WS, 'tools', 'android-sdk');
const JDK = process.env.JAVA_HOME || join(WS, 'tools', 'jdk17');
const BT = join(SDK, 'build-tools', '34.0.0');
const PLATFORM = join(SDK, 'platforms', 'android-34');

const AAPT2 = join(BT, 'aapt2.exe');
const D8 = join(BT, 'd8.bat');
const ZIPALIGN = join(BT, 'zipalign.exe');
const APKSIGNER = join(BT, 'apksigner.bat');
const JAVAC = join(JDK, 'bin', 'javac.exe');
const KEYTOOL = join(JDK, 'bin', 'keytool.exe');
const ANDROID_JAR = join(PLATFORM, 'android.jar');
// Android's android.jar has no java.lang.invoke.LambdaMetafactory, so javac cannot compile
// lambdas / method references against it. The build-tools ship this stub jar to fill the gap
// (this is exactly what AGP adds via core-lambda-stubs).
const LAMBDA_STUBS = join(BT, 'core-lambda-stubs.jar');

for (const [label, p] of [['aapt2', AAPT2], ['d8', D8], ['zipalign', ZIPALIGN],
  ['apksigner', APKSIGNER], ['javac', JAVAC], ['android.jar', ANDROID_JAR]]) {
  if (!existsSync(p)) {
    console.error(`missing ${label}: ${p}`);
    process.exit(2);
  }
}

// Sandbox note: child process stdio must be inherited, not piped (named pipes are blocked).
// Node 20+ refuses to spawn .bat/.cmd directly (EINVAL) for security reasons. Going through
// cmd.exe with a *single command-line string* avoids the argument-quoting mess that
// execFileSync + cmd.exe produces (which yields literal \" in the child command line).
const run = (cmd, args, opts = {}) => {
  const label = `${basename(cmd)} ${args.slice(0, 4).join(' ')}${args.length > 4 ? ' …' : ''}`;
  process.stdout.write(`  > ${label}\n`);
  const isBatch = /\.(bat|cmd)$/i.test(cmd);
  if (isBatch) {
    const q = (s) => (/[\s"]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
    const line = [q(cmd), ...args.map(q)].join(' ');
    execSync(line, { stdio: 'inherit', ...opts });
  } else {
    execFileSync(cmd, args, { stdio: 'inherit', ...opts });
  }
};

// ---------------------------------------------------------------- dirs
const BUILD = process.env.APK_BUILD_DIR || join(WS, '.cache', 'apk-build');
const OUT = join(PROJ, 'dist');
for (const d of [BUILD, OUT, join(BUILD, 'res-compiled'), join(BUILD, 'gen'),
  join(BUILD, 'classes'), join(BUILD, 'dex')]) {
  mkdirSync(d, { recursive: true });
}

const MANIFEST = join(ANDROID, 'AndroidManifest.xml');
const RES = join(ANDROID, 'res');
const SRC = join(ANDROID, 'src');

console.log(`[apk] version ${VERSION_NAME} (${VERSION_CODE})`);

// ---------------------------------------------------------------- 1) aapt2 compile
console.log('[apk] 1/7 aapt2 compile resources');
{
  const resDirs = existsSync(RES) ? readdirSync(RES) : [];
  if (resDirs.length === 0) {
    console.error(`no resource dirs under ${RES}; run tools/make_android_icons.py first`);
    process.exit(2);
  }
  const zip = join(BUILD, 'res.zip');
  rmSync(zip, { force: true });
  const args = ['compile', '--dir', RES, '-o', zip];
  run(AAPT2, args);
}

// ---------------------------------------------------------------- 2) aapt2 link
console.log('[apk] 2/7 aapt2 link');
const unsignedApk = join(BUILD, 'app-unsigned.apk');
{
  rmSync(unsignedApk, { force: true });
  const args = [
    'link',
    '-o', unsignedApk,
    '-I', ANDROID_JAR,
    '--manifest', MANIFEST,
    '-R', join(BUILD, 'res.zip'),
    '--java', join(BUILD, 'gen'),
    '--min-sdk-version', '24',
    '--target-sdk-version', '34',
    '--version-code', String(VERSION_CODE),
    '--version-name', VERSION_NAME,
    '--auto-add-overlay',
  ];
  run(AAPT2, args);
}

// ---------------------------------------------------------------- 3) javac
console.log('[apk] 3/7 javac');
{
  const sources = [];
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.java')) sources.push(p);
    }
  };
  walk(SRC);
  const genDir = join(BUILD, 'gen');
  if (existsSync(join(genDir, 'com', 'mediaconv', 'app'))) walk(genDir);
  console.log(`  sources: ${sources.length}`);
  const boot = existsSync(LAMBDA_STUBS) ? `${ANDROID_JAR}${process.platform === 'win32' ? ';' : ':'}${LAMBDA_STUBS}` : ANDROID_JAR;
  const argFile = join(BUILD, 'javac.args');
  writeFileSync(argFile,
    ['-encoding', 'UTF-8', '-source', '8', '-target', '8',
      '-bootclasspath', boot, '-classpath', ANDROID_JAR,
      '-d', join(BUILD, 'classes'), '-nowarn',
      ...sources].map((s) => (s.includes(' ') ? `"${s}"` : s)).join('\n'), 'utf8');
  run(JAVAC, [`@${argFile}`]);
}

// ---------------------------------------------------------------- 4) d8 -> dex
console.log('[apk] 4/7 d8 (dex)');
{
  const classesDir = join(BUILD, 'classes');
  const classFiles = [];
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.class')) classFiles.push(p);
    }
  };
  walk(classesDir);
  console.log(`  class files: ${classFiles.length}`);
  const outDex = join(BUILD, 'dex');
  rmSync(outDex, { recursive: true, force: true });
  mkdirSync(outDex, { recursive: true });
  const argFile = join(BUILD, 'd8.args');
  writeFileSync(argFile,
    ['--min-api', '24', '--release', '--output', outDex, '--lib', ANDROID_JAR,
      ...classFiles].map((s) => (s.includes(' ') ? `"${s}"` : s)).join('\n'), 'utf8');
  run(D8, [`@${argFile}`]);
}

// ---------------------------------------------------------------- 5) zip dex into apk
console.log('[apk] 5/7 packaging');
{
  const dex = join(BUILD, 'dex', 'classes.dex');
  if (!existsSync(dex)) {
    console.error('classes.dex not produced');
    process.exit(1);
  }
  // aapt2 already built the APK skeleton; splice classes.dex in with the JDK's jar tool
  // (keeps the build dependency-free -- no external zip library needed).
  const jar = join(JDK, 'bin', 'jar.exe');
  const stage = join(BUILD, 'stage');
  rmSync(stage, { recursive: true, force: true });
  mkdirSync(stage, { recursive: true });
  copyFileSync(dex, join(stage, 'classes.dex'));
  run(jar, ['--update', '--file', unsignedApk, '-C', stage, 'classes.dex']);
}

// ---------------------------------------------------------------- 6) zipalign
console.log('[apk] 6/7 zipalign');
const alignedApk = join(BUILD, 'app-aligned.apk');
{
  rmSync(alignedApk, { force: true });
  run(ZIPALIGN, ['-f', '-p', '4', unsignedApk, alignedApk]);
}

// ---------------------------------------------------------------- 7) sign
console.log('[apk] 7/7 signing');
// Keystore location, in order of precedence:
//   1. APK_KEYSTORE env var
//   2. <repo>/.keystore/mediaconv.p12      (normal clone)
//   3. <workspace>/.cache/keystore/...     (our dev layout, kept for compatibility)
// It must never be committed (see .gitignore): losing it changes the APK signing
// certificate, and then users can no longer upgrade in place.
const repoKeystore = join(PROJ, '.keystore', 'mediaconv.p12');
const legacyKeystore = join(WS, '.cache', 'keystore', 'mediaconv.p12');
const keystore = process.env.APK_KEYSTORE
  || (existsSync(legacyKeystore) && !existsSync(repoKeystore) ? legacyKeystore : repoKeystore);
const storePass = process.env.APK_STORE_PASS || 'mediaconv';
const alias = process.env.APK_KEY_ALIAS || 'mediaconv';
mkdirSync(dirname(keystore), { recursive: true });
if (!existsSync(keystore)) {
  console.log('  creating signing key ...');
  run(KEYTOOL, [
    '-genkeypair', '-v',
    '-keystore', keystore,
    '-storetype', 'PKCS12',
    '-storepass', storePass,
    '-keypass', storePass,
    '-alias', alias,
    '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
    '-dname', process.env.APK_DNAME || 'CN=xiaoke, OU=MediaConv, O=xiaoke, L=Local, ST=Local, C=CN',
  ]);
}

const base = `MediaConv-Android-${VERSION_NAME}`;
const signedApk = join(OUT, `${base}.apk`);
rmSync(signedApk, { force: true });
run(APKSIGNER, [
  'sign',
  '--ks', keystore,
  '--ks-type', 'PKCS12',
  '--ks-pass', `pass:${storePass}`,
  '--key-pass', `pass:${storePass}`,
  '--ks-key-alias', alias,
  '--min-sdk-version', '24',
  '--v1-signing-enabled', 'true',
  '--v2-signing-enabled', 'true',
  '--out', signedApk,
  alignedApk,
]);

// verify
run(APKSIGNER, ['verify', '--print-certs', '-v', signedApk]);

const size = statSync(signedApk).size;
console.log(`\n[apk] OK -> ${signedApk}`);
console.log(`[apk] size = ${(size / 1048576).toFixed(2)} MB`);
