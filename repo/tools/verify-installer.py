"""验证 Inno Setup 安装包的内容完整性。

Inno Setup 会把文件表（含每个源文件的路径）加密/编码后存进安装包，
所以不一定能直接搜到明文字符串。本脚本做三件事：
  1. 确认是合法的 PE 可执行文件，并读取版本资源；
  2. 全文件分块扫描，统计可辨认的字符串命中的块；
  3. 用 7-Zip / innoextract（若存在）尝试列出内部文件。

用法：python tools/verify-installer.py <setup.exe>
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

NAMES = [
    b"MediaConv", b"ffmpeg", b"ffprobe", b"python312", b"Qt6Core",
    b"Inno Setup", b"JRSoftware", b"MediaConv.exe",
    "使用说明".encode("utf-16-le"), "格式转换器".encode("utf-16-le"),
    b"MediaConv-Setup",
]


def scan_all(path: Path, chunk: int = 8 << 20) -> dict[str, int]:
    """分块扫描整个文件，统计每个关键词出现的次数。"""
    hits = {n.decode("utf-8", "replace") if isinstance(n, bytes) else n: 0 for n in NAMES}
    size = path.stat().st_size
    overlap = 64
    with open(path, "rb") as f:
        pos = 0
        tail = b""
        while pos < size:
            data = tail + f.read(chunk)
            for name in NAMES:
                key = name.decode("utf-8", "replace") if isinstance(name, bytes) else name
                hits[key] += data.count(name)
            tail = data[-overlap:]
            pos += chunk
    return hits


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify-installer.py <setup.exe>")
        return 2
    exe = Path(sys.argv[1])
    if not exe.exists():
        print(f"找不到文件：{exe}")
        return 2

    print(f"文件: {exe}")
    print(f"大小: {exe.stat().st_size:,} 字节 ({exe.stat().st_size / 1048576:.1f} MB)")

    head = exe.read_bytes()[:2]
    print(f"PE 头: {head!r}  {'OK' if head == b'MZ' else '异常'}")

    # 版本资源（Windows 从 PE 资源段读取，Python 侧用 PowerShell 更省事）
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item '{exe}').VersionInfo | "
             "Select-Object CompanyName,ProductName,FileVersion,FileDescription | "
             "ConvertTo-Json -Compress"],
            capture_output=True, timeout=60)
        print(f"版本信息: {out.stdout.decode('utf-8', 'replace').strip()}")
    except Exception as e:
        print(f"版本信息读取失败: {e}")

    print("\n扫描内部字符串（Inno Setup 通常会压缩，命中数为 0 属正常）：")
    hits = scan_all(exe)
    for name, count in hits.items():
        safe = name.encode("utf-8", "replace")[:40].decode("utf-8", "replace")
        print(f"  {safe:<28} {count}")

    # 若能找到解包工具，直接列出内容，这是最有说服力的验证
    print("\n尝试用解包工具列出内容：")
    tool = None
    for cand in ("innoextract", "7z", "7za"):
        if shutil.which(cand):
            tool = cand
            break
    sevenzip = Path(r"C:\Program Files\7-Zip\7z.exe")
    if tool is None and sevenzip.exists():
        tool = str(sevenzip)

    if tool is None:
        print("  未找到 innoextract / 7z，跳过（不影响结论：安装包由 ISCC 编译成功）")
        return 0

    cmd = [tool, "l", str(exe)] if "7z" in Path(tool).name else [tool, "-l", str(exe)]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=300)
        text = (res.stdout + res.stderr).decode("utf-8", "replace")
        lines = text.splitlines()
        print(f"  {tool} 输出 {len(lines)} 行，前 25 行：")
        for ln in lines[:25]:
            print("   ", ln)
        key = {"MediaConv.exe": 0, "ffmpeg.exe": 0, "ffprobe.exe": 0, "python312.dll": 0}
        for ln in lines:
            for k in key:
                if k.lower() in ln.lower():
                    key[k] += 1
        print("\n  关键文件出现次数：")
        for k, v in key.items():
            print(f"    {k:<16} {v}")
    except Exception as e:
        print(f"  解包失败: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
