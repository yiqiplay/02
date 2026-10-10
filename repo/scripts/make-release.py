"""收集构建产物到「发布包」目录，生成 SHA256 校验和与 Release 正文。

为什么用 Python 而不是 PowerShell：
    PowerShell 5.1 读取 .ps1 时按 ANSI/GBK 解码，中文字符串会乱码；
    而 .NET 格式串 "{1,10:N2}" 里的逗号又会被 PowerShell 当作数组分隔符。
    这个脚本里有大量中文与格式化文本，用 Python 更省心，而且跨平台。

用法（在仓库根目录）：
    python scripts/make-release.py
    python scripts/make-release.py --version 1.0.1
    python scripts/make-release.py --repo-url https://github.com/你的用户名/MediaConv
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent                      # 仓库根
PARENT = REPO.parent                    # 仓库的上一级目录


def find_dist() -> Path | None:
    """定位构建产物目录。

    不同人的目录布局不一样，所以按优先级逐个尝试：
      A) 仓库自己就是项目根      <repo>/dist
      B) 仓库放在项目内部        <repo>/MediaConverter/dist
      C) 仓库与项目平级          <parent>/MediaConverter/dist, <parent>/dist
      D) 仓库被放在某个整理目录里 <grandparent>/MediaConverter/dist
    """
    candidates = [
        REPO / "dist",
        REPO / "MediaConverter" / "dist",
        PARENT / "MediaConverter" / "dist",
        PARENT / "dist",
        PARENT.parent / "MediaConverter" / "dist",
        PARENT.parent / "dist",
    ]
    for c in candidates:
        if c.is_dir() and any(c.glob("MediaConv-*")):
            return c
    # 目录存在但没有产物，也返回它，好让调用方给出更准确的提示
    for c in candidates:
        if c.is_dir():
            return c
    return None


def find_iss() -> Path | None:
    """定位 installer.iss（用于读取版本号）。"""
    for c in (
        REPO / "tools" / "installer.iss",
        REPO / "MediaConverter" / "tools" / "installer.iss",
        PARENT / "MediaConverter" / "tools" / "installer.iss",
        PARENT.parent / "MediaConverter" / "tools" / "installer.iss",
    ):
        if c.exists():
            return c
    return None


def default_outdir() -> Path:
    """发布包输出目录：优先放在 <parent>/发布包（与仓库平级）。"""
    for base in (PARENT, PARENT.parent):
        if base.is_dir():
            return base / "发布包"
    return REPO / "发布包"


def detect_version(dist: Path | None) -> str:
    """从 installer.iss 或产物文件名推断版本号。"""
    iss = find_iss()
    if iss is not None:
        m = re.search(r'MyAppVersion\s+"([^"]+)"', iss.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    if dist:
        for f in dist.glob("MediaConv-Setup-*.exe"):
            m = re.search(r"Setup-([0-9][\w.\-]*)\.exe$", f.name)
            if m:
                return m.group(1)
    return "1.0.0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / 1048576:.2f} MB"
    if n >= 1 << 10:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


RELEASE_NOTES = """# MediaConv v{version}

图片 / 视频 / 音频 格式转换工具，Windows 桌面版 + Android 手机版。
**完全离线运行，不联网、不上传文件。**

## 下载

| 平台 | 文件 | 大小 | 要求 |
|---|---|---|---|
| Windows 安装包 | `{setup_name}` | {setup_size} | Windows 10 及以上 |
| Windows 免安装 | `{portable_name}` | {portable_size} | 解压即用，无需安装 |
| Android | `{apk_name}` | {apk_size} | Android 7.0 (API 24) 及以上 |

## 能转什么

- **图片 23 种输出**：JPEG / PNG / WebP / HEIC / AVIF / APNG / GIF / BMP / TIFF /
  ICO / ICNS / PDF / DDS / JPEG 2000 / TGA / QOI 等，可读入 75 种扩展名
- **视频 20 种组合**：MP4(H.264 / H.265) / MKV / WebM(VP9 / VP8 / AV1) /
  MOV(H.264 / ProRes) / AVI / MPEG-TS / FLV / WMV / OGV / 3GP / MPEG-2 / 动图
- **音频 12 种**：MP3 / M4A / AAC / WAV / FLAC / Opus / OGG / WMA / AC3 /
  AMR / M4R / AIFF，可直接从视频提取音轨

格式列表是启动时探测本机真实能力生成的，不会列出"转了会失败"的格式。

## 安装说明

**Windows**：程序未做代码签名，SmartScreen 可能提示「未知发布者」，
点「更多信息」→「仍要运行」即可。exe 属性里的发布者为 `xiaoke`。

**Android**：首次安装需允许「安装未知来源应用」。
输出文件保存在相册的 `Movies` / `Pictures` / `Music` 下的 `MediaConv` 文件夹。

## 验证情况

- 电脑版端到端测试 **111 项全部通过**
  （自造样本 55 项 + 从公网下载的真实素材 56 项）
- 每项测试都用 ffprobe / Pillow **读回输出并断言真实编码器**，
  不是「文件存在即通过」
- 手机版的运行时行为尚未在真机上验证，详见仓库的测试说明

## 文件校验

下载后可用 `校验和.txt` 中的 SHA256 校验文件完整性：

```
{checksum_preview}
```

---

完整改动记录见 [CHANGELOG.md]({repo_url}/blob/main/CHANGELOG.md)　·　
使用问题见 [常见问题]({repo_url}/blob/main/docs/FAQ.md)
"""


def display_width(s: str) -> int:
    """估算字符串显示宽度：中日韩字符按 2 列算。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, width: int, align: str = "left") -> str:
    """按显示宽度补齐（不能用 str.ljust，中文会错位）。"""
    gap = max(0, width - display_width(s))
    return (" " * gap + s) if align == "right" else (s + " " * gap)


def make_zip(portable_dir: Path, outdir: Path, version: str) -> dict | None:
    """把免安装目录打成 zip（已存在则跳过）。

    用 zipfile 而不是 Compress-Archive：PowerShell 5.1 的实现在处理
    中文文件名和大目录时容易出问题。
    """
    if not portable_dir.is_dir():
        return None
    target = outdir / f"MediaConv-Portable-{version}.zip"
    if target.exists() and target.stat().st_size > 0:
        print(f"  [已存在] {target.name:<40} {human(target.stat().st_size):>10}")
    else:
        print(f"  正在压缩免安装版（约 500 MB，需要一两分钟）…")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in portable_dir.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(portable_dir.parent))
        print(f"  [已生成] {target.name:<40} {human(target.stat().st_size):>10}")
    return {
        "name": target.name,
        "path": target,
        "size": target.stat().st_size,
        "sha256": sha256(target),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="", help="版本号，默认自动检测")
    ap.add_argument("--repo-url", default="https://github.com/USERNAME/MediaConv",
                    help="仓库地址，用于生成 Release 正文里的链接")
    ap.add_argument("--outdir", default="", help="发布包输出目录，默认 <上级>/发布包")
    a = ap.parse_args()

    dist = find_dist()
    if dist is None:
        print("找不到构建产物目录（dist）。请先执行构建：")
        print("  powershell -ExecutionPolicy Bypass -File tools/build-desktop.ps1 -Clean")
        print("  powershell -ExecutionPolicy Bypass -File tools/build-installer.ps1 -SkipPortable")
        print("  node tools/build-apk.mjs")
        return 1

    version = a.version or detect_version(dist)
    outdir = Path(a.outdir) if a.outdir else default_outdir()
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"仓库     : {REPO}")
    print(f"构建产物 : {dist}")
    print(f"版本号   : {version}")
    print(f"发布包   : {outdir}")
    print()

    # ---------------------------------------------------------- 收集
    wanted = [
        (dist / f"MediaConv-Setup-{version}.exe", "Windows 安装包"),
        (dist / f"MediaConv-Android-{version}.apk", "Android 安装包"),
    ]

    collected: list[dict] = []
    print("收集产物：")
    for path, label in wanted:
        if not path.exists():
            print(f"  [缺少] {path.name}  （{label}）")
            continue
        dst = outdir / path.name
        shutil.copy2(path, dst)
        size = dst.stat().st_size
        collected.append({"name": dst.name, "path": dst, "size": size, "sha256": sha256(dst)})
        print(f"  [已收集] {dst.name:<40} {human(size):>10}")

    # 免安装版打成 zip（体积最大，但很多人只要这个）
    portable = make_zip(dist / "MediaConv", outdir, version)
    if portable:
        collected.append(portable)

    if not collected:
        print()
        print("没有找到任何产物。请先构建，或检查版本号是否正确。")
        return 1

    # ---------------------------------------------------------- 校验和
    name_w = max(display_width(c["name"]) for c in collected) + 2
    size_w = max(len(human(c["size"])) for c in collected) + 2
    lines = [
        f"MediaConv v{version} - 文件校验（SHA256）",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        pad("文件", name_w) + pad("大小", size_w, "right") + "  校验和",
        "-" * (name_w + size_w + 66),
    ]
    for c in collected:
        lines.append(f"{pad(c['name'], name_w)}{pad(human(c['size']), size_w, 'right')}  {c['sha256']}")
    lines += [
        "",
        "校验方法：",
        "  Windows PowerShell:  Get-FileHash <文件> -Algorithm SHA256",
        "  Windows 命令行:      certutil -hashfile <文件> SHA256",
        "  Linux / macOS:       sha256sum <文件>",
    ]
    sum_file = outdir / "校验和.txt"
    sum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n已写入 {sum_file.name}")

    # ---------------------------------------------------------- Release 正文
    by_name = {c["name"]: c for c in collected}
    setup = by_name.get(f"MediaConv-Setup-{version}.exe")
    apk = by_name.get(f"MediaConv-Android-{version}.apk")
    zipped = by_name.get(f"MediaConv-Portable-{version}.zip")

    notes = RELEASE_NOTES.format(
        version=version,
        setup_name=setup["name"] if setup else f"MediaConv-Setup-{version}.exe",
        setup_size=human(setup["size"]) if setup else "—",
        portable_name=zipped["name"] if zipped else f"MediaConv-Portable-{version}.zip",
        portable_size=human(zipped["size"]) if zipped else "—",
        apk_name=apk["name"] if apk else f"MediaConv-Android-{version}.apk",
        apk_size=human(apk["size"]) if apk else "—",
        repo_url=a.repo_url.rstrip("/"),
        checksum_preview="\n".join(f"{c['sha256']}  {c['name']}" for c in collected),
    )
    notes_file = outdir / "更新说明.md"
    notes_file.write_text(notes, encoding="utf-8")
    print(f"已写入 {notes_file.name}")

    # ---------------------------------------------------------- 汇总
    print("\n===== 发布包内容 =====")
    for f in sorted(outdir.iterdir()):
        if f.is_file():
            print(f"  {f.name:<40} {human(f.stat().st_size):>10}")

    print("\n下一步：")
    print("  1. 核对版本号与文件大小是否合理")
    print("  2. 上传源码：cd repo ; git add . ; git commit ; git push")
    print(f"  3. 创建 tag v{version} 并发布，把上面 {len(collected)} 个文件作为附件上传")
    print(f"  4. 正文用「发布包/{notes_file.name}」的内容")
    print("\n详细步骤见 文档/发布指南.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
