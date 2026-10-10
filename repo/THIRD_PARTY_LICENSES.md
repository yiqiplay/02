# 第三方组件与许可证

本项目的源代码采用 MIT 许可，但**分发的二进制包**内置了第三方组件，
其中 FFmpeg 采用 GPL v3，因此二进制发行包整体受 GPL v3 约束。

---

## 内置的可执行文件

### FFmpeg / FFprobe

| 项目 | 说明 |
|---|---|
| 版本 | `N-127252-ga25ba44c0c` (2026-10-08) |
| 来源 | https://github.com/BtbN/FFmpeg-Builds |
| 许可证 | **GNU General Public License v3** |
| 源码 | https://git.ffmpeg.org/ffmpeg.git |
| 官网 | https://ffmpeg.org/ |

该构建启用了 GPL 组件（libx264、libx265、x264、x265 等），因此为 GPL 版本。
启用 `--enable-gpl` 的构建不可改为更宽松的许可证。

**为什么选 GPL 构建？**
H.264 / H.265 编码需要 libx264 / libx265，这两个库是 GPL 的。
如果改用 LGPL 构建，就会失去最常用的两种视频编码能力。

**再分发要求**：随包提供本文件、保留 FFmpeg 的版权声明，
并提供获取对应源码的方式（上面的源码链接）。

---

## Python 依赖

| 组件 | 版本 | 许可证 | 项目地址 |
|---|---|---|---|
| PySide6 (Qt for Python) | 6.12.0 | LGPL v3 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| shiboken6 | 6.12.0 | LGPL v3 | 同上 |
| Pillow | 12.3.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| pillow-heif | 1.8.0 | BSD-3-Clause | https://github.com/bigcat88/pillow_heif |
| pillow-avif-plugin | 1.6.0 | BSD-3-Clause | https://github.com/fdintino/pillow-avif-plugin |
| PyInstaller（仅构建期） | 6.22.3 | GPL v2 + 例外条款 | https://github.com/pyinstaller/pyinstaller |

### 关于 PySide6 (Qt)

Qt 采用 LGPL v3。以 LGPL 组件进行**动态链接**分发是被允许的，
但需满足：保留版权声明、提供 LGPL 全文、并允许用户替换该库
（本项目的 PySide6 以独立 DLL 形式放在 `_internal/PySide6/` 下，满足可替换要求）。

---

## pillow-heif 携带的原生库

| 库 | 许可证 |
|---|---|
| libheif | LGPL v3 |
| libde265 | LGPL v3 |
| libx265 | GPL v2（或商业许可） |
| libaom | BSD-2-Clause |

其中 **libx265 为 GPL v2**，这也是 HEIC 编码能力的来源。
若不希望引入 GPL 依赖，可在构建时移除 `pillow-heif`，届时 HEIC 将不可用。

---

## Android 版

手机版**不包含任何第三方二进制库**，全部使用 Android 平台自带 API：

| API | 用途 |
|---|---|
| `BitmapFactory` / `Bitmap` | 图片解码与编码 |
| `MediaExtractor` | 媒体拆包 |
| `MediaCodec` | 硬件编解码 |
| `MediaMuxer` | 封装为 MP4 / WebM |
| `MediaMetadataRetriever` | 读取媒体信息 |

因此 APK 仅 65 KB，且不引入额外的许可证义务。

---

## 构建工具（不随产品分发）

| 工具 | 许可证 |
|---|---|
| Inno Setup | 修改版 BSD |
| Android SDK Build-Tools | Apache 2.0 |
| JDK (OpenJDK) | GPL v2 + Classpath 例外 |

---

## 合规检查清单

如果你要再分发本项目的二进制包，请确认：

- [ ] 随包附带本文件与 `LICENSE`
- [ ] 保留 `_internal/bin/ffmpeg.exe` 与 `ffprobe.exe` 的版权信息（不要剥离）
- [ ] 提供 FFmpeg 源码获取方式（本文件已包含）
- [ ] 若修改了 FFmpeg 本身，需一并公开修改后的源码
- [ ] 不要移除 `_internal/PySide6/` 下的 Qt DLL（否则违反 LGPL 的可替换要求）
- [ ] 不要声称本软件完全由你原创——需保留第三方组件的版权声明
