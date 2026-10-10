# MediaConv 端到端测试报告

- 被测程序：`D:\Deepseekharness\MediaConverter\dist\MediaConv\MediaConv.exe`
- 结果：通过 55 / 失败 0 / 跳过 0（共 55 项）

| 测试项 | 结果 | 说明 |
|---|---|---|
| info 列出图片格式 | ✅ PASS |  |
| info 列出视频/音频格式 | ✅ PASS |  |
| info 找到内置 ffmpeg | ✅ PASS |  |
| list 输出格式代号 | ✅ PASS |  |
| 图片 PNG → JPEG | ✅ PASS | 800x600 JPEG 15,122B |
| 图片 PNG(透明) → JPEG 白底 | ✅ PASS | 400x400 JPEG 9,844B |
| 图片 JPEG → PNG | ✅ PASS | 640x400 PNG 38,915B |
| 图片 PNG → WebP | ✅ PASS | 800x600 WEBP 5,532B |
| 图片 PNG → HEIC（iPhone 格式） | ✅ PASS | 800x600 HEIF 13,618B |
| 图片 PNG → AVIF | ✅ PASS | 800x600 AVIF 3,180B |
| 图片 PNG → BMP | ✅ PASS | 800x600 BMP 1,440,054B |
| 图片 PNG → TIFF | ✅ PASS | 800x600 TIFF 13,038B |
| 图片 JPEG → ICO（多尺寸） | ✅ PASS | 256x160 ICO 16,015B |
| 图片 PNG → PDF | ✅ PASS | PDF 头校验 |
| 图片 PNG → JPEG2000 | ✅ PASS | 800x600 JPEG2000 27,489B |
| 图片 PNG → TGA | ✅ PASS | 800x600 TGA 1,440,044B |
| 图片 PNG → QOI | ✅ PASS | 800x600 QOI 15,335B |
| 图片 PNG → 缩放 50% | ✅ PASS | 400x300 JPEG 7,823B |
| 图片 PNG → 指定宽度 320 | ✅ PASS | 320x240 PNG 5,307B |
| 图片 灰度 PNG → GIF | ✅ PASS | 300x200 GIF 1,922B |
| HEIC 输入 → JPEG（iPhone 照片场景） | ✅ PASS | 800x600 |
| 动图 GIF → 动图 WebP（保留帧） | ✅ PASS | 12 帧 |
| 重复转换不覆盖已有文件 | ✅ PASS | sample_rgb_converted.webp / sample_rgb_converted_1.webp |
| 插件状态自检 | ✅ PASS |  |
| 视频 MP4(H.264) → MKV(H.264) | ✅ PASS | h264/aac 640x360 505,167B |
| 视频 MP4(H.264) → MP4(H.265) | ✅ PASS | hevc/aac 640x360 558,862B |
| 视频 MP4(H.264) → WebM(VP9) | ✅ PASS | vp9/opus 640x360 548,032B |
| 视频 MKV(VP9) → MP4(H.264) | ✅ PASS | h264/aac 640x360 574,980B |
| 视频 AVI(MPEG-4) → MP4(H.264) | ✅ PASS | h264/aac 640x360 656,979B |
| 视频 MP4 → MOV(ProRes) | ✅ PASS | prores/pcm_s16le 640x360 7,468,579B |
| 视频 MP4 → MPEG-TS | ✅ PASS | h264/aac 640x360 545,764B |
| 视频 MP4 → FLV | ✅ PASS | h264/aac 640x360 507,745B |
| 视频 MP4 → WMV | ✅ PASS | wmv2/wmav2 640x360 1,220,117B |
| 视频 MP4 → OGV(Theora) | ✅ PASS | theora/vorbis 640x360 979,627B |
| 视频 MP4 → 3GP | ✅ PASS | h264/aac 640x360 506,989B |
| 视频 MP4 → MPEG-2 | ✅ PASS | mpeg2video/mp2 640x360 1,179,648B |
| 视频 MP4 → GIF 动图 | ✅ PASS | gif/- 426x240 521,530B |
| 视频 MP4 → WebP 动图 | ✅ PASS | webp_anim/- 640x360 587,432B |
| 无声视频 → MP4 | ✅ PASS | 无音轨也正常 |
| 竖屏视频方向保持 | ✅ PASS | 360x640 |
| 降分辨率到 360p（宽度取偶数） | ✅ PASS | 640x360 |
| 裁剪片段（1-3 秒） | ✅ PASS | 时长 2.00s |
| 音频 MP4 → MP3 | ✅ PASS | mp3 97,845B |
| 音频 MP4 → M4A | ✅ PASS | aac 87,125B |
| 音频 MP4 → FLAC | ✅ PASS | flac 235,142B |
| 音频 MP4 → WAV | ✅ PASS | pcm_s16le 352,878B |
| 音频 MP4 → Opus | ✅ PASS | opus 100,270B |
| 音频 MP4 → AMR（手机录音格式） | ✅ PASS | amr_nb 6,438B |
| 音频 MP4 → AAC | ✅ PASS | aac 86,849B |
| 音频 MP4 → M4R（iPhone 铃声） | ✅ PASS | aac 87,125B |
| 音频 WAV → MP3 | ✅ PASS | mp3 49,571B |
| 音频 WAV → OGG | ✅ PASS | vorbis 10,757B |
| 批量转换多个文件 | ✅ PASS | 5/5 成功 |
| 损坏文件优雅报错（不崩溃） | ✅ PASS | 无法读取图片（broken.png）：cannot identify image file 'D:\\Deepseekharness\\.cache\\test-out\\brok |
| 非法格式名给出明确提示 | ✅ PASS | 不认识的目标格式：不存在的格式（可用 --list 查看） |
