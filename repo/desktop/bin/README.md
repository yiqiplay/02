# desktop/bin

此目录存放程序内置的 FFmpeg 可执行文件：

```
desktop/bin/ffmpeg.exe
desktop/bin/ffprobe.exe
```

## 为什么不提交到仓库

这两个文件合计约 **320 MB**。如果提交进 Git：

- 克隆仓库会变得非常慢（几百 MB 的历史无法轻易瘦身）
- GitHub 对单文件有 100 MB 的硬限制，超了直接拒绝推送

所以 `.gitignore` 把它们排除了，改由 **Releases** 页面分发已打包好的成品。

## 怎么获取

任选一个来源下载后解压，把 `ffmpeg.exe` 与 `ffprobe.exe` 放到本目录：

| 来源 | 文件名 | 说明 |
|---|---|---|
| [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases) | `ffmpeg-master-latest-win64-gpl.zip` | 功能最全，本项目使用的就是它 |
| [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) | `ffmpeg-release-essentials.zip` | 体积较小，常用编码器齐全 |

解压后 `bin/` 子目录里就有这两个文件。本项目内置版本为：

```
ffmpeg version N-127252-ga25ba44c0c
```

## 也可以不放在这里

程序按以下顺序查找 ffmpeg：

1. 本目录（`bin/`）
2. 环境变量 `MEDIACONV_FFMPEG` 指向的路径
3. 系统 PATH
4. Windows 常见安装位置

所以如果你系统里已经装好 ffmpeg，直接运行源码也能用。

## 许可证

FFmpeg 采用 **GPL v3**（本项目使用启用了 libx264/libx265 的 GPL 构建）。
再分发时请遵守其许可条款，详见仓库根目录的
[THIRD_PARTY_LICENSES.md](../../THIRD_PARTY_LICENSES.md)。
