# 贡献指南

感谢你愿意改进这个项目。本文说明如何搭建环境、代码规范，以及提交前需要做什么。

## 目录

- [报告问题](#报告问题)
- [搭建开发环境](#搭建开发环境)
- [代码规范](#代码规范)
- [提交 Pull Request](#提交-pull-request)
- [添加新格式支持](#添加新格式支持)

---

## 报告问题

提交 Issue 前请先搜索是否已有相同问题。报告 bug 时请尽量包含：

| 信息 | 怎么获取 |
|---|---|
| 程序版本 | 运行 `MediaConv.exe version` |
| 系统版本 | Windows 设置 → 系统 → 关于 |
| 本机支持的格式 | 运行 `MediaConv.exe info` |
| 出错的文件 | 格式、大小、编码（可用 `ffprobe 文件` 查看） |
| 完整报错 | 命令行下重现时的完整输出 |
| 手机版问题 | 机型、Android 版本，以及 `adb logcat -s DragScrollView` 的输出 |

**能稳定重现的最小例子**比长篇描述有用得多。

---

## 搭建开发环境

### 电脑版

```powershell
# 1) 依赖（装在工作区而不是系统 Python，避免污染环境）
node tools/pip-install.mjs ..\.cache\pylibs PySide6-Essentials pillow-heif pillow-avif-plugin
node tools/normalize-wheels.mjs ..\.cache\pylibs

# 2) 设置环境变量
$env:PYTHONPATH = "..\.cache\pylibs"

# 3) 直接用源码运行，不必每次打包
python desktop\MediaConv.py            # 开图形界面
python tools\run-source-cli.py info    # 命令行
```

FFmpeg 放到 `desktop\bin\ffmpeg.exe` 与 `desktop\bin\ffprobe.exe`。
没有也能跑，只是视频/音频功能不可用。

### 手机版

需要 JDK 17 与 Android SDK（build-tools 34 + platform 34）：

```bash
node tools/build-apk.mjs
```

产物在 `dist/MediaConv-Android-<版本>.apk`。

本项目**刻意不使用 Gradle 与 AndroidX**：
APK 构建走 `aapt2 → javac → d8 → zipalign → apksigner`，
全部使用平台 API，好处是构建无需联网解析依赖、产物只有 65 KB。
如果你要引入 AndroidX，请先在 Issue 里讨论。

---

## 代码规范

### 通用

- **注释写"为什么"，不写"是什么"。** 例如不要写 `// 遍历列表`，
  而要写 `// 这里的插件是惰性导入的，不先 init 的话 Image.SAVE 几乎是空的`
- 遇到平台坑（Windows 编码、cmd 怪癖、Android 版本差异）时，
  **把踩坑原因写在注释里**，避免后人重复踩
- 提交信息用中文或英文均可，但要说明**改了什么、为什么**

### Python

- 面向 Python 3.12，使用 `from __future__ import annotations`
- 类型标注尽量写全
- 公共函数要有 docstring
- 路径处理一律用 `pathlib.Path`
- 子进程调用在 Windows 上要隐藏控制台窗口（`FFmpeg._no_window_kwargs()`）

### Java（Android）

- 目标 API 24，不要使用更高版本才有的 API
  （例如 `MediaMuxer(FileDescriptor, int)` 需要 API 26，改用文件路径）
- 不要引入 AndroidX 依赖
- 界面用代码构建（`buildUi()`），不用 XML 布局
- 字符串用中文，注释解释平台差异

---

## 提交 Pull Request

1. Fork 并新建分支：`git checkout -b fix/heic-alpha-channel`
2. 改动尽量聚焦，一个 PR 解决一件事
3. **跑通两套测试**：

   ```bash
   python tools/test_suite.py             # 55 项
   python tools/test-with-webfiles.py     # 56 项，需先下载素材
   ```

4. 如果加了新的格式支持或修了 bug，请在 `CHANGELOG.md` 的
   「未发布」区块加一条
5. 在 PR 描述里说明：改了什么、为什么、怎么验证的

### 关于测试

新增格式支持时，请同时添加测试用例。测试的判定标准是
**读回输出并断言真实属性**，不是"文件存在"：

```python
# 好的写法
info = FFmpeg.probe(out)
assert info.vcodec == "hevc", f"期望 hevc，实际 {info.vcodec}"

# 不好的写法
assert out.exists()
```

---

## 添加新格式支持

### 添加图片格式

1. 在 `desktop/mediaconv/Formats.py` 的 `_IMAGE_META` 里加一条：

   ```python
   "WEBP2": ImageFormat("WEBP2", ".webp2", "WebP 2（.webp2）",
                        supports_alpha=True, notes="实验格式"),
   ```

2. 如果该格式需要额外插件，在 `register_image_plugins()` 里注册
3. 在 `tools/test_suite.py` 里加测试用例
4. 运行 `MediaConv.exe info` 确认它出现在列表里

不需要修改界面代码——下拉框是遍历能力矩阵自动生成的。

### 添加视频/音频格式

1. 在 `desktop/mediaconv/Formats.py` 的 `VIDEO_TARGETS` 里加一条
   `VideoFormat`，指定容器 muxer、视频编码器、音频编码器
2. 如果编码器有特殊参数（CRF 范围、preset 名称），
   在 `desktop/mediaconv/Video.py` 的 `_quality_args()` 里补分支
3. 加测试用例并确认 `MediaConv.exe list` 能看到新代号

程序会检查 ffmpeg 是否真的支持该编码器，不支持会自动从列表里隐藏，
所以不必担心列出不可用的格式。

---

## 许可证

提交代码即表示你同意以本项目的 [MIT 许可证](LICENSE) 发布你的贡献。

注意：二进制发行包内置 FFmpeg（GPL v3），详见
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
