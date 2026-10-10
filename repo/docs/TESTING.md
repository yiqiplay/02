# 测试说明

本项目的测试原则：**不把"文件存在"当作通过标准**。
每个转换结果都会用 ffprobe 或 Pillow 读回来，断言真实的编码器、分辨率、帧数。

## 测试组成

| 测试脚本 | 项数 | 输入来源 |
|---|---|---|
| `tools/test_suite.py` | 55 | 脚本自动生成的样本 |
| `tools/test-with-webfiles.py` | 56 | 从公网下载的真实素材 |
| **合计** | **111** | |

两套都跑在**打包之后的 exe** 上，而不是源码——这样能同时验证打包配置是否正确。

---

## 一、自造样本测试（55 项）

样本由 `tools/make_samples.py` 与 `tools/make_video_samples.py` 生成，
覆盖全部输出格式，优点是格式齐全、可控。

```
--- 能力自检 (4) ---
info 列出图片格式 / 列出视频音频格式 / 找到内置 ffmpeg / list 输出格式代号

--- 图片转换 (16) ---
PNG → JPEG, PNG(透明) → JPEG 白底, JPEG → PNG, PNG → WebP,
PNG → HEIC, PNG → AVIF, PNG → BMP, PNG → TIFF, JPEG → ICO(多尺寸),
PNG → PDF, PNG → JPEG2000, PNG → TGA, PNG → QOI,
PNG → 缩放 50%, PNG → 指定宽度 320, 灰度 PNG → GIF

--- 图片边界 (4) ---
HEIC 输入 → JPEG（模拟 iPhone 照片）, 动图 GIF → 动图 WebP（校验保留 12 帧）,
重复转换不覆盖已有文件, 插件状态自检

--- 视频转换 (14) ---
MP4 → MKV(H.264) / MP4(H.265) / WebM(VP9) / MOV(ProRes) / MPEG-TS / FLV /
      WMV / OGV(Theora) / 3GP / MPEG-2 / GIF 动图 / WebP 动图
MKV(VP9) → MP4(H.264),  AVI(MPEG-4) → MP4(H.264)
每一项都断言输出编码器与输入不同，确保真的重编码了

--- 视频边界 (4) ---
无声视频 → MP4, 竖屏视频方向保持, 降分辨率到 360p（宽度取偶）, 裁剪 1-3 秒

--- 音频 (10) ---
MP4 → MP3 / M4A / FLAC / WAV / Opus / AMR / AAC / M4R
WAV → MP3 / OGG
断言：输出不含视频轨、音频编码符合预期

--- 健壮性 (3) ---
批量转换多文件, 损坏文件优雅报错（不崩溃）, 非法格式名给出明确提示
```

---

## 二、真实网络素材测试（56 项）

自造样本"太干净"，为了暴露真实世界的问题，这一套改用公网下载的真实文件。

素材共 **24 个文件 / 43 MB**，下载时逐个校验文件头——
很多站点返回 404 页面而不是 404 状态码，不校验就会把 HTML 当图片测试。

### 素材清单

| 类别 | 文件 | 关键特征 |
|---|---|---|
| 图片 | JPEG | 1200×800，来自 picsum.photos |
| 图片 | PNG | 550×368 |
| 图片 | WebP | 550×404（Google 官方示例） |
| 图片 | GIF | 128×128（Pillow 测试图集） |
| 图片 | BMP / TIFF / ICO | Pillow 测试图集 |
| 图片 | **HEIC** | 1440×960（Nokia HEIF 官方示例） |
| 图片 | **AVIF** | 1024×770（libavif 官方测试图） |
| 视频 | MP4 | H.264 640×360 10s |
| 视频 | WebM | VP8 640×360 10s |
| 视频 | AVI | MPEG-4 640×360 13s |
| 视频 | MOV | H.264 640×360 13s |
| 视频 | FLV | FLV1 640×360 13s |
| 视频 | WMV | MS-MPEG4v3 640×360 13s |
| 视频 | MPG | MPEG-2 640×360 13s |
| 视频 | TS | MPEG-2 640×360 13s |
| 视频 | 3GP | H.264 640×360 13s |
| 音频 | MP3 / WAV / FLAC / OGG / M4A / AAC | 约 106 秒 |

### 覆盖的输出

- **图片 22 项**：HEIC→JPEG/PNG、AVIF→JPEG/PNG、GIF→PNG/WebP/JPEG、
  BMP→PNG/JPEG/TIFF、TIFF→JPEG/PNG、ICO→PNG/JPEG、JPEG→WEBP/PNG/AVIF/HEIC 等
- **视频 14 项**：9 种输入容器 → MP4(H.264) / MP4(H.265) / MKV / WebM(VP9) / AVI / GIF 动图
- **音频 15 项**：6 种音频格式两两互转
- **边界 5 项**：专门验证"缺少目标所需流"时的提示是否人类可读

### 这一套测试实际发现的问题

公网下载的测试短片**全部只有视频轨、没有音轨**，因此触发了自造样本从未覆盖的路径：

> 给无音轨视频提取音频时，程序只抛出
> `Error opening output files: Invalid argument`

修复后改为提前检查并按情况提示，详见 [CHANGELOG](CHANGELOG.md)。

这条经验也说明了为什么值得维护两套测试：
自造样本保证**格式覆盖度**，真实素材保证**贴近实际使用**。

---

## 手工验证过的项目

自动化测试覆盖不到、但已人工确认的：

| 项目 | 方法 | 结果 |
|---|---|---|
| 图形界面能启动 | 离屏模式创建窗口并读取状态栏 | 通过，状态栏显示 23 种图片 / 32 种视频音频格式 |
| exe 子系统类型 | 解析 PE 头 `Subsystem` 字段 | `2` (WINDOWS_GUI)，启动不产生控制台窗口 |
| 安装包有效性 | 检查 PE 头、`Inno Setup` 标识、版本资源 | 通过，发布者为 `xiaoke` |
| 命令行管道调用 | `cmd /c "MediaConv.exe list > out.txt"` | 输出正确写入文件 |
| APK 结构与签名 | `aapt2 dump badging` / `apksigner verify` / `dexdump` | 包名、版本、中文名正确；v2+v3 签名通过 |
| APK 代码完整性 | `dexdump` 检索关键方法 | `DragScrollView`、`transcodeVideo` 等均在包内 |

## 未验证的部分（如实说明）

- **手机版的运行时行为未做真机测试。** 开发环境没有 Android 设备，
  Android SDK 未安装模拟器组件，系统中也没有第三方安卓运行环境。
  界面滑动、硬件编码器兼容性、相册写入可见性等均属于
  "静态验证通过（已确认编译进 dex）、运行时未验证"。
- Mac / Linux 打包未验证。

## 如何运行

```bash
# 需要：Python 3.12 + 工作区依赖（见 README 构建章节）

# 自造样本测试（会自动生成样本）
python tools/make_samples.py tests/samples
python tools/make_video_samples.py tests/samples
python tools/test_suite.py --exe dist/MediaConv/MediaConv.exe

# 真实网络素材测试（需要联网下载）
node tools/fetch-testfiles.mjs .cache/webtest
node tools/fetch-missing-formats.mjs .cache/webtest
python tools/test-with-webfiles.py \
    --exe dist/MediaConv/MediaConv.exe \
    --indir .cache/webtest \
    --outdir .cache/webtest-out
```

测试报告会写入 `tests/test-report.md` 与 `tests/web-test-report.md`。
