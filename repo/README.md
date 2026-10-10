<div align="center">

# 格式转换器 · MediaConv

**图片 / 视频 / 音频 格式转换工具** · Windows 桌面版 + Android 手机版
本软件由我和Deepseek共同制作

完全离线运行 · 不联网 · 不上传文件

[![Release](https://img.shields.io/badge/release-v1.0.0-blue.svg)](../../releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B%20%7C%20Android%207.0%2B-lightgrey.svg)](#-下载安装)
[![Tests](https://img.shields.io/badge/tests-111%20passed-brightgreen.svg)](docs/TESTING.md)

</div>

---

## 这是什么

一个把「图片、视频、音频互相转换格式」这件事做完整的工具。市面上同类工具要么只支持图片、
要么要联网上传、要么偷偷加水印——这个程序**全程在你自己的电脑/手机上完成**，
断网也能用。

- **电脑版**：PySide6 图形界面 + 命令行，内置完整版 FFmpeg，图片走 Pillow
- **手机版**：原生 Android 应用，图片用系统编解码器，视频调用硬件编解码器

## 能转什么

格式列表不是写死的，程序启动时会**探测本机真实能力**再生成——不会出现"列出来了却转不动"。

### 图片（23 种输出）

| 分类 | 格式 |
|---|---|
| 日常通用 | **JPEG** · **PNG** · **WebP** · **HEIC** · **AVIF** |
| 动图 | **APNG** · **GIF**（保留多帧） |
| 无损 / 专业 | BMP · TIFF · TGA · PCX · PPM · SGI · QOI · JPEG 2000 |
| 图标 / 特殊 | ICO（自动多尺寸）· ICNS · DDS · PDF · MPO · Palm · WMF · XBM |

可读入 **75 种扩展名**，包含 iPhone 的 `.heic`，以及 `.avif` `.psd` `.jp2` `.dds` `.qoi` 等。

### 视频（20 种输出组合）

| 容器 | 编码 |
|---|---|
| **MP4** | H.264（兼容性最好）· H.265（体积小约 40%） |
| **MKV** | H.264 · H.265 |
| **WebM** | VP9 · VP8 · AV1 |
| **MOV** | H.264 · ProRes（专业剪辑） |
| **AVI** | MPEG-4 · MJPEG |
| 其它 | MPEG-TS · FLV · WMV · OGV(Theora) · 3GP · MPEG-2 |
| 动图 | GIF · WebP · APNG（自动调色板优化） |

可读入 `mp4 mkv webm avi mov wmv flv ts m2ts vob rmvb rm 3gp ogv mxf dv` 等。

### 音频（12 种输出）

MP3 · M4A · AAC · WAV · FLAC · Opus · OGG · WMA · AC3 · **AMR** · **M4R（iPhone 铃声）** · AIFF

可直接从视频里提取音轨。

## 下载安装

到 [**Releases**](../../releases) 页面下载（下载包体积较大，不放在源码里）：

| 平台 | 文件 | 大小 | 说明 |
|---|---|---|---|
| Windows | `MediaConv-Setup-1.0.0.exe` | 约 133 MB | 安装包，可创建快捷方式与右键菜单 |
| Android | `MediaConv-Android-1.0.0.apk` | 约 65 KB | 要求 Android 7.0（API 24）及以上 |

> **Windows 提示**：程序未做代码签名，SmartScreen 可能提示"未知发布者"，
> 先以管理员权限运行后选择「更多信息」→「仍要运行」即可。exe 属性里的发布者信息为 `xiaoke`。

## 快速上手

### 图形界面

1. 双击 `MediaConv.exe`（或从开始菜单打开）
2. 添加文件：点「添加文件」/「添加文件夹」，或**直接把文件拖进窗口**
3. 右侧设置目标格式与参数
4. 点「开始转换」，完成后点「打开输出目录」

### 命令行

```bash
# 查看本机支持的全部格式
MediaConv.exe info

# 转成 WebM（VP9）
MediaConv.exe convert 视频.mp4 -t webm_vp9

# 整个文件夹的图片批量转 WebP
MediaConv.exe convert D:\照片 -t WEBP -q 85

# 视频压缩并降到 720p
MediaConv.exe convert 视频.mov -t mp4_h264 --scale 720 --preset small

# 提取音轨
MediaConv.exe convert 视频.mp4 -t mp3

# 裁剪第 10 秒到第 30 秒
MediaConv.exe convert 视频.mp4 -t mp4_h264 --trim 10-30

# 输出 JSON 报告，方便脚本调用
MediaConv.exe convert *.png -t WEBP --json-out report.json
```

常用参数：

| 参数 | 说明 |
|---|---|
| `-t, --target` | 目标格式（代号或扩展名） |
| `-o, --outdir` | 输出目录，默认与源文件同目录 |
| `-q, --quality` | 质量 1-100 |
| `--preset` | 画质档位 `high` / `balanced` / `small` / `tiny` |
| `--scale` | 视频分辨率 `keep` / `2160` / `1440` / `1080` / `720` / `480` / `360` |
| `--fps` | 帧率，`0` 表示保持原始 |
| `--resize` | 图片缩放 `percent=50` / `width=1920` / `max=2000` |
| `--copy` | 仅换容器不重编码（极快） |
| `--overwrite` | 允许覆盖同名文件 |

## 项目结构

```
MediaConv/
├── desktop/                     电脑版
│   ├── MediaConv.py             统一入口（无参数开界面，带参数走命令行）
│   ├── mediaconv/
│   │   ├── Formats.py           格式能力探测与格式矩阵
│   │   ├── Images.py            图片转换引擎（Pillow + HEIF/AVIF 插件）
│   │   ├── Video.py             视频/音频转换引擎（FFmpeg 参数构建与校验）
│   │   ├── FFmpeg.py            ffmpeg/ffprobe 定位、探测、进度解析
│   │   ├── Jobs.py              任务队列（GUI 与 CLI 共用同一套逻辑）
│   │   ├── Cli.py               命令行界面
│   │   └── Gui.py               PySide6 图形界面
│   └── bin/                     内置的 ffmpeg.exe / ffprobe.exe（不提交到仓库）
├── android/                     手机版（纯平台 API，无 AndroidX 依赖）
│   └── app/src/com/mediaconv/app/
│       ├── MainActivity.java    界面与流程
│       ├── DragScrollView.java  自行接管触控的滚动容器
│       ├── ImageConverter.java  图片转换
│       └── VideoConverter.java  视频转码（MediaCodec + MediaMuxer）
├── tools/                       构建与测试脚本
├── docs/                        文档
└── tests/                       测试样本生成与报告
```

## 从源码构建

### 前置要求

| 用途 | 需要 |
|---|---|
| 电脑版 | Windows 10+、Python 3.12 |
| 手机版 | JDK 17、Android SDK（build-tools 34 + platform 34）、Node.js |
| 安装包 | Inno Setup 6 |

### 步骤

```powershell
# 1) 安装 Python 依赖到工作区
node tools/pip-install.mjs ..\.cache\pylibs PySide6-Essentials pillow-heif pillow-avif-plugin
node tools/normalize-wheels.mjs ..\.cache\pylibs

# 2) 下载 FFmpeg（GPL 构建）并放进 desktop\bin\
#    任选一个来源，解压后把 ffmpeg.exe 与 ffprobe.exe 放到 desktop\bin\
#    https://www.gyan.dev/ffmpeg/builds/           (ffmpeg-release-essentials.zip)
#    https://github.com/BtbN/FFmpeg-Builds/releases (ffmpeg-master-latest-win64-gpl.zip)

# 3) 打包电脑版
powershell -ExecutionPolicy Bypass -File tools/build-desktop.ps1 -Clean

# 4) 生成安装包
powershell -ExecutionPolicy Bypass -File tools/build-installer.ps1

# 5) 打包手机版 APK
node tools/build-apk.mjs

# 6) 跑测试
python tools/test_suite.py            # 自造样本：55 项
python tools/test-with-webfiles.py    # 真实网络素材：56 项
```

## 测试

**两套端到端测试共 111 项，全部通过。**

| 测试 | 项数 | 说明 |
|---|---|---|
| `tools/test_suite.py` | 55 | 自造样本，覆盖全部 23 种图片格式与 20 种视频组合 |
| `tools/test-with-webfiles.py` | 56 | 从公网下载的真实素材（含 HEIC / AVIF / ProRes / FLV / WMV 等） |

关键点：**每个输出都用 ffprobe 或 Pillow 读回来校验真实编码器**，
而不是"文件存在就算通过"。例如 MP4→H.265 会断言 `codec_name == hevc`
且带 Apple 兼容的 `hvc1` 标签。

报告见 [`docs/TESTING.md`](docs/TESTING.md)。

## 设计说明

**为什么用 onedir 而不是单文件 exe？**
程序内置完整版 FFmpeg（约 320 MB）。单文件模式每次启动都要把这几百 MB 解压到临时目录，
启动要十几秒；onedir 是秒开的。

**为什么格式列表是运行时探测的？**
不硬编码"我以为支持的格式"，而是启动时向 Pillow / ffmpeg / MediaCodecList 询问真实
能力。换一个 ffmpeg 构建、换一台手机，列表自动跟着变。

**为什么手机版不用 FFmpeg？**
Android 自带 `MediaCodec` / `MediaExtractor` / `MediaMuxer`，能直接调用硬件编解码器，
速度快、发热低，而且 APK 只有 65 KB。代价是输出容器以 MP4 / WebM 为主。

**转换失败不会中断整个队列。**
每个文件独立捕获异常并记录可读的原因，坏文件只影响它自己。

## 已知限制

- **手机版**输出容器为 MP4（H.264 / H.265）与 WebM（VP8 / VP9），
  可用编码取决于机型硬件；电脑版支持全部 20 种组合
- **Mac / Linux** 暂未打包，但代码本身是跨平台的（Path 处理、ffmpeg 定位均已兼容）
- 视频转 GIF 时建议帧率 ≤ 15 fps，否则文件会很大（GIF 格式本身的限制）
- 未做代码签名，Windows SmartScreen 会提示未知发布者

## 许可证与第三方组件

本项目的**源代码**采用 [MIT 许可证](LICENSE)。

程序分发的二进制版本内置了 **FFmpeg**，它采用 **GPL v3** 许可。
因此**分发的安装包/免安装包整体受 GPL v3 约束**，但并不影响你使用 MIT 许可使用本项目源码。

FFmpeg 源码可从这里获取：

- 官方仓库：https://git.ffmpeg.org/ffmpeg.git
- 本项目使用的 Windows 构建：https://github.com/BtbN/FFmpeg-Builds

其它第三方组件：

| 组件 | 许可证 |
|---|---|
| PySide6 (Qt for Python) | LGPL v3 |
| Pillow | MIT-CMU |
| pillow-heif | BSD-3-Clause |
| libheif | LGPL v3 |

详见 [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)。

## 贡献

欢迎提交 Issue 与 Pull Request，请先看 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 免责声明

本工具仅用于格式转换。请确保你对所处理的文件拥有合法权利，
并遵守当地法律法规与相关平台的服务条款。

---

<div align="center">

**如果这个工具帮到了你，欢迎点一个 ⭐ Star**

</div>
