# 真实网络素材转换测试报告

- 被测程序：`D:\Deepseekharness\MediaConverter\dist\MediaConv\MediaConv.exe`
- 素材来源：公网下载的真实图片/视频/音频（25 个文件）
- 结果：通过 56 / 失败 0 / 跳过 0（共 56 项）

| 测试项 | 结果 | 说明 |
|---|---|---|
| 图片 jpg_from_web.jpg → WEBP | ✅ PASS | WEBP 1200x800 147KB |
| 图片 jpg_from_web.jpg → PNG | ✅ PASS | PNG 1200x800 1057KB |
| 图片 jpg_from_web.jpg → AVIF | ✅ PASS | AVIF 1200x800 156KB |
| 图片 jpg_from_web.jpg → HEIC | ✅ PASS | HEIF 1200x800 328KB |
| 图片 png_from_web.png → JPEG | ✅ PASS | JPEG 550x368 64KB |
| 图片 png_from_web.png → WEBP | ✅ PASS | WEBP 550x368 40KB |
| 图片 webp_from_web.webp → JPEG | ✅ PASS | JPEG 550x404 106KB |
| 图片 webp_from_web.webp → PNG | ✅ PASS | PNG 550x404 513KB |
| 图片 gif_from_web.gif → PNG | ✅ PASS | PNG 128x128 14KB |
| 图片 gif_from_web.gif → WEBP | ✅ PASS | WEBP 128x128 6KB |
| 图片 gif_from_web.gif → JPEG | ✅ PASS | JPEG 128x128 7KB |
| 图片 bmp_from_web.bmp → PNG | ✅ PASS | PNG 128x128 30KB |
| 图片 bmp_from_web.bmp → JPEG | ✅ PASS | JPEG 128x128 6KB |
| 图片 bmp_from_web.bmp → TIFF | ✅ PASS | TIFF 128x128 38KB |
| 图片 tiff_from_web.tiff → JPEG | ✅ PASS | JPEG 128x128 6KB |
| 图片 tiff_from_web.tiff → PNG | ✅ PASS | PNG 128x128 30KB |
| 图片 ico_from_web.ico → PNG | ✅ PASS | PNG 16x16 1KB |
| 图片 ico_from_web.ico → JPEG | ✅ PASS | JPEG 16x16 1KB |
| 图片 heic_from_web.heic → JPEG | ✅ PASS | JPEG 1440x960 539KB |
| 图片 heic_from_web.heic → PNG | ✅ PASS | PNG 1440x960 2703KB |
| 图片 avif_from_web.avif → JPEG | ✅ PASS | JPEG 1024x770 96KB |
| 图片 avif_from_web.avif → PNG | ✅ PASS | PNG 1024x770 502KB |
| 视频 mp4_from_web.mp4 → webm_vp9 | ✅ PASS | vp9 640x360 10.0s 1069KB |
| 视频 mp4_from_web.mp4 → mp4_h265 | ✅ PASS | hevc 640x360 10.0s 1350KB |
| 视频 mp4_from_web.mp4 → mkv_h264 | ✅ PASS | h264 640x360 10.0s 1273KB |
| 视频 webm_from_web.webm → mp4_h264 | ✅ PASS | h264 640x360 10.0s 1336KB |
| 视频 webm_from_web.webm → avi_mpeg4 | ✅ PASS | mpeg4 640x360 10.0s 2467KB |
| 视频 avi_from_web.avi → mp4_h264 | ✅ PASS | h264 640x360 13.3s 895KB |
| 视频 avi_from_web.avi → mkv_h264 | ✅ PASS | h264 640x360 13.3s 895KB |
| 视频 mov_from_web.mov → mp4_h264 | ✅ PASS | h264 640x360 13.3s 612KB |
| 视频 flv_from_web.flv → mp4_h264 | ✅ PASS | h264 640x360 13.3s 809KB |
| 视频 wmv_from_web.wmv → mp4_h264 | ✅ PASS | h264 640x360 13.3s 920KB |
| 视频 mpg_from_web.mpg → mp4_h264 | ✅ PASS | h264 640x360 13.3s 725KB |
| 视频 ts_from_web.ts → mp4_h264 | ✅ PASS | h264 640x360 13.3s 725KB |
| 视频 3gp_from_web.3gp → mp4_h264 | ✅ PASS | h264 640x360 13.3s 612KB |
| 视频 mp4_from_web.mp4 → gif_anim | ✅ PASS | gif 426x240 10.2s 2891KB |
| 音频 mp3_from_web.mp3 → m4a | ✅ PASS | aac 105.8s 2499KB |
| 音频 mp3_from_web.mp3 → flac | ✅ PASS | flac 105.8s 28408KB |
| 音频 mp3_from_web.mp3 → wav | ✅ PASS | pcm_s16le 105.8s 18221KB |
| 音频 mp3_from_web.mp3 → ogg_audio | ✅ PASS | vorbis 105.8s 2241KB |
| 音频 wav_from_web.wav → mp3 | ✅ PASS | mp3 105.8s 2481KB |
| 音频 wav_from_web.wav → opus | ✅ PASS | opus 105.8s 2469KB |
| 音频 wav_from_web.wav → aac | ✅ PASS | aac 106.0s 2511KB |
| 音频 flac_from_web.flac → mp3 | ✅ PASS | mp3 105.8s 2481KB |
| 音频 flac_from_web.flac → m4a | ✅ PASS | aac 105.8s 2498KB |
| 音频 ogg_from_web.ogg → mp3 | ✅ PASS | mp3 105.8s 2481KB |
| 音频 ogg_from_web.ogg → wav | ✅ PASS | pcm_s16le 105.8s 18221KB |
| 音频 m4a_from_web.m4a → mp3 | ✅ PASS | mp3 105.8s 2481KB |
| 音频 m4a_from_web.m4a → flac | ✅ PASS | flac 105.8s 21453KB |
| 音频 aac_from_web.aac → mp3 | ✅ PASS | mp3 105.8s 2481KB |
| 音频 aac_from_web.aac → wav | ✅ PASS | pcm_s16le 105.8s 18228KB |
| 无音轨视频 → 提取 MP3 | ✅ PASS | 这个文件没有音轨，无法提取音频：mp4_from_web.mp4 |
| 无音轨视频 → 提取 M4A | ✅ PASS | 这个文件没有音轨，无法提取音频：mov_from_web.mov |
| 无音轨视频 → 提取 FLAC | ✅ PASS | 这个文件没有音轨，无法提取音频：avi_from_web.avi |
| 纯音频 → MP4 | ✅ PASS | 这个文件没有视频轨，无法转成视频：mp3_from_web.mp3 |
| 纯音频 → WebM | ✅ PASS | 这个文件没有视频轨，无法转成视频：ogg_from_web.ogg |
