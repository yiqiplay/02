// 从 GitHub 仓库抓取缺失格式的真实测试图（GIF / BMP / TIFF / AVIF / ICO），
// 走 gh-proxy 加速。每个候选都校验文件头，防止把 404 页面当成图片。
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const OUT = process.argv[2] || 'D:/Deepseekharness/.cache/webtest';
mkdirSync(OUT, { recursive: true });

const PROXY = 'https://gh-proxy.com/';

// [保存名, 仓库内路径, 期望的文件头检测函数]
const TARGETS = [
  // Pillow 官方测试图集，覆盖 gif / bmp / tiff / ico
  ['gif_from_web.gif', 'python-pillow/Pillow/main/Tests/images/hopper.gif', 'gif'],
  ['gif_from_web.gif', 'python-pillow/Pillow/main/Tests/images/animate.gif', 'gif'],
  ['bmp_from_web.bmp', 'python-pillow/Pillow/main/Tests/images/hopper.bmp', 'bmp'],
  ['bmp_from_web.bmp', 'python-pillow/Pillow/main/Tests/images/rgb32bf.bmp', 'bmp'],
  ['tiff_from_web.tiff', 'python-pillow/Pillow/main/Tests/images/hopper.tif', 'tiff'],
  ['tiff_from_web.tiff', 'python-pillow/Pillow/main/Tests/images/lena_g4.tif', 'tiff'],
  ['ico_from_web.ico', 'python-pillow/Pillow/main/Tests/images/sample.ico', 'ico'],
  ['ico_from_web.ico', 'python-pillow/Pillow/main/Tests/images/hopper.ico', 'ico'],
  ['png_from_web.png', 'python-pillow/Pillow/main/Tests/images/hopper.png', 'png'],
  ['jpg_from_web.jpg', 'python-pillow/Pillow/main/Tests/images/hopper.jpg', 'jpg'],
  // AVIF：用 libavif 仓库里的测试图
  ['avif_from_web.avif', 'AOMediaCodec/libavif/main/tests/data/paris_icc_exif_xmp.avif', 'avif'],
  ['avif_from_web.avif', 'AOMediaCodec/libavif/main/tests/data/kodim03_yuv420_8bpc.avif', 'avif'],
  ['avif_from_web.avif', 'AOMediaCodec/libavif/main/tests/data/sofa_grid1x5_420.avif', 'avif'],
];

function check(buf, kind) {
  const h = buf.subarray(0, 12);
  const hex = h.toString('hex');
  switch (kind) {
    case 'gif':
      return hex.startsWith('47494638');
    case 'bmp':
      return hex.startsWith('424d');
    case 'tiff':
      return hex.startsWith('49492a00') || hex.startsWith('4d4d002a');
    case 'ico':
      return hex.startsWith('00000100') || hex.startsWith('00000200');
    case 'png':
      return hex.startsWith('89504e47');
    case 'jpg':
      return hex.startsWith('ffd8ff');
    case 'avif':
      // ISO-BMFF: 4 字节长度 + 'ftyp' + brand
      return hex.slice(8, 16) === '66747970' && /61766966|6d696631/.test(hex.slice(16, 32));
    default:
      return true;
  }
}

const got = new Map();
for (const [name, path, kind] of TARGETS) {
  const raw = `https://raw.githubusercontent.com/${path}`;
  const url = PROXY + raw;
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 40000);
    const res = await fetch(url, { redirect: 'follow', signal: ac.signal });
    clearTimeout(t);
    if (!res.ok) {
      console.log(`  HTTP${res.status}  ${name.padEnd(22)} ${path}`);
      continue;
    }
    const buf = Buffer.from(await res.arrayBuffer());
    if (!check(buf, kind)) {
      console.log(`  头不符    ${name.padEnd(22)} ${path}  head=${buf.subarray(0, 8).toString('hex')}`);
      continue;
    }
    // 同名已存在就保留更大的那个（通常质量更好）
    const file = join(OUT, name);
    if (existsSync(file) && readFileSync(file).length >= buf.length) {
      console.log(`  保留原文件 ${name.padEnd(22)} (已有 ${readFileSync(file).length}B > ${buf.length}B)`);
      continue;
    }
    writeFileSync(file, buf);
    console.log(`  OK        ${name.padEnd(22)} ${String(buf.length).padStart(9)}B`);
  } catch (e) {
    console.log(`  失败      ${name.padEnd(22)} ${e.name}`);
  }
}

console.log('\n当前目录内容：');
for (const f of readdirSafe(OUT)) {
  console.log('  ', f);
}

function readdirSafe(dir) {
  try {
    return require('node:fs').readdirSync(dir);
  } catch {
    return [];
  }
}
