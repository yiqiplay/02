// 逐个测试候选测试素材 URL 是否真的能下载，并校验文件头与目标格式是否一致。
// 这一步很关键：很多站点返回 404 页面而不是 404 状态码，
// 必须检查 magic bytes，否则会把 HTML 错误页当图片拿去转换。
import { existsSync, mkdirSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const OUT = process.argv[2] || 'D:/Deepseekharness/.cache/webtest';
mkdirSync(OUT, { recursive: true });

// 各格式的文件头特征（用于确认下载到的确实是这个格式）
const MAGIC = {
  jpg: [[0xff, 0xd8, 0xff]],
  png: [[0x89, 0x50, 0x4e, 0x47]],
  gif: [[0x47, 0x49, 0x46, 0x38]],
  bmp: [[0x42, 0x4d]],
  tiff: [[0x49, 0x49, 0x2a, 0x00], [0x4d, 0x4d, 0x00, 0x2a]],
  webp: [[0x52, 0x49, 0x46, 0x46]],   // RIFF....WEBP
  avif: [[0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70]],
  heic: [[0x00, 0x00, 0x00], ],        // 后面跟 ftyp，单独判断
  ico: [[0x00, 0x00, 0x01, 0x00]],
  mp4: [[0x00, 0x00, 0x00], ],
  webm: [[0x1a, 0x45, 0xdf, 0xa3]],
  mkv: [[0x1a, 0x45, 0xdf, 0xa3]],
  avi: [[0x52, 0x49, 0x46, 0x46]],
  mov: [[0x00, 0x00, 0x00]],
  mpg: [[0x00, 0x00, 0x01, 0xba], [0x00, 0x00, 0x01, 0xb3]],
  flv: [[0x46, 0x4c, 0x56, 0x01]],
  wmv: [[0x30, 0x26, 0xb2, 0x75]],
  '3gp': [[0x00, 0x00, 0x00]],
  ts: [[0x47]],
  mp3: [[0x49, 0x44, 0x33], [0xff, 0xfb], [0xff, 0xf3], [0xff, 0xf2]],
  wav: [[0x52, 0x49, 0x46, 0x46]],
  flac: [[0x66, 0x4c, 0x61, 0x43]],
  ogg: [[0x4f, 0x67, 0x67, 0x53]],
  m4a: [[0x00, 0x00, 0x00]],
  aac: [[0xff, 0xf1], [0xff, 0xf9], [0x41, 0x44, 0x49, 0x46]],
};

function matches(ext, buf) {
  const pats = MAGIC[ext];
  if (!pats) return true;
  for (const p of pats) {
    if (buf.length >= p.length && p.every((b, i) => buf[i] === b)) return true;
  }
  // heic/avif/mp4/mov/3gp/m4a 都是 ISO-BMFF，检查 ftyp box
  if (['heic', 'avif', 'mp4', 'mov', '3gp', 'm4a'].includes(ext)) {
    const s = buf.subarray(4, 12).toString('latin1');
    if (s.startsWith('ftyp')) return true;
  }
  return false;
}

const CANDIDATES = [
  // 扩展名可能与我最初猜的不同，这里全部试一遍
  ['jpg', 'https://filesamples.com/samples/image/jpeg/sample_1920x1080.jpeg'],
  ['jpg', 'https://filesamples.com/samples/image/jpeg/sample_640x426.jpeg'],
  ['png', 'https://filesamples.com/samples/image/png/sample_1920x1080.png'],
  ['png', 'https://filesamples.com/samples/image/png/sample_640x426.png'],
  ['gif', 'https://filesamples.com/samples/image/gif/sample_640x426.gif'],
  ['gif', 'https://filesamples.com/samples/image/gif/sample1.gif'],
  ['bmp', 'https://filesamples.com/samples/image/bmp/sample_640x426.bmp'],
  ['bmp', 'https://filesamples.com/samples/image/bmp/sample1.bmp'],
  ['tiff', 'https://filesamples.com/samples/image/tiff/sample_640x426.tiff'],
  ['tiff', 'https://filesamples.com/samples/image/tiff/sample1.tiff'],
  ['webp', 'https://filesamples.com/samples/image/webp/sample_1920x1080.webp'],
  ['avif', 'https://filesamples.com/samples/image/avif/sample1.avif'],
  ['avif', 'https://filesamples.com/samples/image/avif/sample_640x426.avif'],
  ['heic', 'https://filesamples.com/samples/image/heic/sample1.heic'],
  ['heic', 'https://filesamples.com/samples/image/heic/sample_640x426.heic'],
  ['ico', 'https://filesamples.com/samples/image/ico/sample_256x256.ico'],
  ['jpg', 'https://picsum.photos/1200/800.jpg'],
  ['webp', 'https://www.gstatic.com/webp/gallery/1.webp'],
  ['webp', 'https://www.gstatic.com/webp/gallery/2.webp'],
  ['png', 'https://www.gstatic.com/webp/gallery/1.png'],
  // 视频
  ['mp4', 'https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.mp4'],
  ['mp4', 'https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4'],
  ['webm', 'https://test-videos.co.uk/vids/bigbuckbunny/webm/vp8/360/Big_Buck_Bunny_360_10s_1MB.webm'],
  ['mkv', 'https://test-videos.co.uk/vids/bigbuckbunny/mkv/360/Big_Buck_Bunny_360_10s_1MB.mkv'],
  ['avi', 'https://filesamples.com/samples/video/avi/sample_640x360.avi'],
  ['mov', 'https://filesamples.com/samples/video/mov/sample_640x360.mov'],
  ['mpg', 'https://filesamples.com/samples/video/mpg/sample_640x360.mpg'],
  ['flv', 'https://filesamples.com/samples/video/flv/sample_640x360.flv'],
  ['wmv', 'https://filesamples.com/samples/video/wmv/sample_640x360.wmv'],
  ['3gp', 'https://filesamples.com/samples/video/3gp/sample_640x360.3gp'],
  ['ts', 'https://filesamples.com/samples/video/ts/sample_640x360.ts'],
  // 音频
  ['mp3', 'https://filesamples.com/samples/audio/mp3/sample3.mp3'],
  ['wav', 'https://filesamples.com/samples/audio/wav/sample3.wav'],
  ['flac', 'https://filesamples.com/samples/audio/flac/sample3.flac'],
  ['ogg', 'https://filesamples.com/samples/audio/ogg/sample3.ogg'],
  ['m4a', 'https://filesamples.com/samples/audio/m4a/sample3.m4a'],
  ['aac', 'https://filesamples.com/samples/audio/aac/sample3.aac'],
];

const good = [];
for (const [ext, url] of CANDIDATES) {
  const label = url.split('/').slice(-2).join('/');
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 45000);
    const res = await fetch(url, { redirect: 'follow', signal: ac.signal });
    clearTimeout(t);
    if (!res.ok) {
      console.log(`  404/HTTP${res.status}  ${ext.padEnd(5)} ${label}`);
      continue;
    }
    const buf = Buffer.from(await res.arrayBuffer());
    if (!matches(ext, buf)) {
      const head = buf.subarray(0, 8).toString('hex');
      console.log(`  格式不符  ${ext.padEnd(5)} ${label}  实际头=${head} (${buf.length}B)`);
      continue;
    }
    const name = `${ext}_from_web.${ext}`;
    const file = join(OUT, name);
    writeFileSync(file, buf);
    console.log(`  OK        ${ext.padEnd(5)} ${String(buf.length).padStart(9)}B  -> ${name}`);
    good.push({ ext, url, name, size: buf.length });
  } catch (e) {
    console.log(`  失败      ${ext.padEnd(5)} ${label}  ${e.name}`);
  }
}

console.log(`\n成功下载 ${good.length} 个真实素材到 ${OUT}`);
writeFileSync(join(OUT, '_manifest.json'), JSON.stringify(good, null, 2), 'utf8');
