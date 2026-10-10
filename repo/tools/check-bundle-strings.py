"""检查 PyInstaller 打包产物里是否包含指定的字符串。

用途：确认源码改动真的进了 exe（而不是只改了源码没重新打包）。
原理：PyInstaller 的 onedir 产物把 Python 模块放在 _internal/base_library.zip 与
PKG 归档里，这里直接扫描这些容器里的字节。

用法：python tools/check-bundle-strings.py <dist目录> "<字符串1>" ["<字符串2>" ...]
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def iter_payload_bytes(dist: Path):
    """产出 (来源描述, 字节) 对，覆盖 exe 本体和所有可能的归档。"""
    exe = dist / "MediaConv.exe"
    if exe.exists():
        yield f"{exe.name}", exe.read_bytes()

    internal = dist / "_internal"
    if internal.is_dir():
        for p in internal.rglob("*"):
            if not p.is_file():
                continue
            low = p.name.lower()
            # 只扫可能含有 Python 代码的容器，避免读几百 MB 的 dll
            if low.endswith((".zip", ".pyz", ".pkg")):
                yield str(p.relative_to(dist)), p.read_bytes()

    # base_library.zip 里的 .pyc
    blz = internal / "base_library.zip"
    if blz.exists():
        with zipfile.ZipFile(blz) as z:
            for name in z.namelist():
                if name.endswith(".pyc"):
                    yield f"base_library.zip:{name}", z.read(name)


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: check-bundle-strings.py <dist目录> "<字符串>" ...')
        return 2
    dist = Path(sys.argv[1])
    needles = sys.argv[2:]
    if not dist.is_dir():
        print(f"目录不存在：{dist}")
        return 2

    blobs = list(iter_payload_bytes(dist))
    print(f"扫描 {len(blobs)} 个容器，查找 {len(needles)} 个字符串\n")

    results = {n: [] for n in needles}
    for origin, data in blobs:
        for n in needles:
            if n.encode("utf-8") in data:
                results[n].append(origin)

    bad = 0
    for n in needles:
        hits = results[n]
        status = "找到" if hits else "未找到"
        if not hits:
            bad += 1
        where = f"  ({hits[0]})" if hits else ""
        print(f"  [{status}] {n}{where}")

    print()
    if bad:
        print(f"有 {bad} 个字符串不在打包产物里 —— 可能忘了重新打包")
        return 1
    print("全部字符串均已打包进产物")
    return 0


if __name__ == "__main__":
    sys.exit(main())
