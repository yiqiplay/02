// 探测公网测试素材源的可达性，为真实格式测试挑选可用链接。
// 只做 HEAD/Range 探测，不下载完整文件。
// Usage: node probe-testfiles.mjs
const CANDIDATES = {
  // ---------------- 视频 ----------------
  'video/mp4': [
    'https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.mp4',
    'https://sample-videos.com/video321/mp4/240/big_buck_bunny_240p_1mb.mp4',
    'https://filesamples.com/samples/video/mp4/sample_640x360.mp4',
    'https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4',
  ],
  'video/webm': [
    'https://test-videos.co.uk/vids/bigbuckbunny/webm/vp8/360/Big_Buck_Bunny_360_10s_1MB.webm',
    'https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.webm',
    'https://filesamples.com/samples/video/webm/sample_640x360.webm',
  ],
  'video/x-matroska': [
    'https://test-videos.co.uk/vids/bigbuckbunny/mkv/360/Big_Buck_Bunny_360_10s_1MB.mkv',
    'https://filesamples.com/samples/video/mkv/sample_640x360.mkv',
  ],
  'video/x-msvideo': [
    'https://filesamples.com/samples/video/avi/sample_640x360.avi',
    'https://test-videos.co.uk/vids/bigbuckbunny/avi/360/Big_Buck_Bunny_360_10s_1MB.avi',
  ],
  'video/quicktime': [
    'https://filesamples.com/samples/video/mov/sample_640x360.mov',
    'https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.mov',
  ],
  'video/mpeg': [
    'https://filesamples.com/samples/video/mpg/sample_640x360.mpg',
  ],
  'video/x-flv': [
    'https://filesamples.com/samples/video/flv/sample_640x360.flv',
  ],
  'video/x-ms-wmv': [
    'https://filesamples.com/samples/video/wmv/sample_640x360.wmv',
  ],
  'video/3gpp': [
    'https://filesamples.com/samples/video/3gp/sample_640x360.3gp',
  ],
  'video/mp2t': [
    'https://filesamples.com/samples/video/ts/sample_640x360.ts',
  ],
  // ---------------- 图片 ----------------
  'image/jpeg': [
    'https://filesamples.com/samples/image/jpeg/sample_1920x1080.jpg',
    'https://picsum.photos/800/600.jpg',
  ],
  'image/png': [
    'https://filesamples.com/samples/image/png/sample_1920x1080.png',
    'https://picsum.photos/800/600.png',
  ],
  'image/webp': [
    'https://filesamples.com/samples/image/webp/sample_1920x1080.webp',
    'https://www.gstatic.com/webp/gallery/1.webp',
  ],
  'image/gif': [
    'https://filesamples.com/samples/image/gif/sample_640x426.gif',
    'https://upload.wikimedia.org/wikipedia/commons/d/d3/Newtons_cradle_animation_book_2.gif',
  ],
  'image/bmp': [
    'https://filesamples.com/samples/image/bmp/sample_640x426.bmp',
  ],
  'image/tiff': [
    'https://filesamples.com/samples/image/tiff/sample_640x426.tiff',
  ],
  'image/heic': [
    'https://filesamples.com/samples/image/heic/sample1.heic',
    'https://github.com/nokiatech/heif/raw/gh-pages/content/images/autumn_1440x960.heic',
  ],
  'image/avif': [
    'https://filesamples.com/samples/image/avif/sample1.avif',
    'https://github.com/AOMediaCodec/av1-avif/raw/master/testFiles/Netflix/avatars/Netflix_0001.avif',
  ],
  'image/x-icon': [
    'https://filesamples.com/samples/image/ico/sample_256x256.ico',
  ],
  'image/svg+xml': [
    'https://upload.wikimedia.org/wikipedia/commons/4/42/Shaqi_jrvej.svg',
  ],
  // ---------------- 音频 ----------------
  'audio/mpeg': [
    'https://filesamples.com/samples/audio/mp3/sample3.mp3',
    'https://www.learningcontainer.com/wp-content/uploads/2020/02/Kalimba.mp3',
  ],
  'audio/wav': [
    'https://filesamples.com/samples/audio/wav/sample3.wav',
  ],
  'audio/flac': [
    'https://filesamples.com/samples/audio/flac/sample3.flac',
  ],
  'audio/ogg': [
    'https://filesamples.com/samples/audio/ogg/sample3.ogg',
  ],
  'audio/mp4': [
    'https://filesamples.com/samples/audio/m4a/sample3.m4a',
  ],
  'audio/aac': [
    'https://filesamples.com/samples/audio/aac/sample3.aac',
  ],
};

const timeoutMs = 25000;

async function probe(url) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    let res = await fetch(url, { method: 'HEAD', redirect: 'follow', signal: ac.signal });
    let size = Number(res.headers.get('content-length') || 0);
    if (!res.ok) {
      // 有些站点不支持 HEAD，退回 Range 取 1 字节
      res = await fetch(url, { headers: { Range: 'bytes=0-0' }, redirect: 'follow', signal: ac.signal });
      if (res.ok || res.status === 206) {
        const cr = res.headers.get('content-range');
        size = cr ? Number(cr.split('/')[1]) : 0;
      }
    }
    if (res.body) await res.body.cancel().catch(() => {});
    return { ok: res.ok || res.status === 206, status: res.status, size };
  } catch (e) {
    return { ok: false, status: 0, size: 0, err: e.name };
  } finally {
    clearTimeout(t);
  }
}

const results = {};
for (const [kind, urls] of Object.entries(CANDIDATES)) {
  results[kind] = [];
  for (const u of urls) {
    const r = await probe(u);
    const mark = r.ok ? 'OK  ' : 'FAIL';
    console.log(`${mark} ${String(r.size || 0).padStart(10)}  ${kind.padEnd(20)} ${u}`);
    if (r.ok) results[kind].push({ url: u, size: r.size });
  }
}

console.log('\n===== 可用汇总 =====');
for (const [kind, list] of Object.entries(results)) {
  if (list.length === 0) console.log(`  ${kind.padEnd(20)} 无可用链接`);
  else console.log(`  ${kind.padEnd(20)} ${list.length} 个可用，首选 ${(list[0].size / 1024).toFixed(0)} KB`);
}
