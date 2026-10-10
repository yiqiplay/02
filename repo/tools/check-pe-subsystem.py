"""检查 PE 可执行文件的子系统类型，确认 exe 是否会创建控制台窗口。

Windows PE 头里的 Subsystem 字段：
    2 = IMAGE_SUBSYSTEM_WINDOWS_GUI    -> 双击/快捷方式启动不创建控制台窗口
    3 = IMAGE_SUBSYSTEM_WINDOWS_CUI    -> 启动时自动创建（或附加）控制台窗口

用法：python tools/check-pe-subsystem.py <exe> [<exe>...]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

SUBSYSTEMS = {
    1: "NATIVE (driver)",
    2: "WINDOWS_GUI  -> no console window is created   [GOOD]",
    3: "WINDOWS_CUI  -> a console window is created    [BAD]",
    5: "OS/2 console",
    7: "POSIX console",
    9: "WINDOWS_CE GUI",
    10: "EFI application",
}


def read_subsystem(path: Path) -> int | None:
    """解析 PE 头，返回 Subsystem 值。"""
    with open(path, "rb") as f:
        data = f.read(4096)  # DOS 头 + PE 头足够

    if data[:2] != b"MZ":
        return None
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return None

    # COFF 头 20 字节，之后是可选头
    opt_off = e_lfanew + 4 + 20
    magic = struct.unpack_from("<H", data, opt_off)[0]
    if magic == 0x10B:       # PE32
        sub_off = opt_off + 68
    elif magic == 0x20B:     # PE32+
        sub_off = opt_off + 68
    else:
        return None
    return struct.unpack_from("<H", data, sub_off)[0]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-pe-subsystem.py <exe> [<exe>...]")
        return 2

    bad = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"[缺失] {p}")
            bad += 1
            continue
        sub = read_subsystem(p)
        desc = SUBSYSTEMS.get(sub, f"unknown({sub})")
        flag = "OK " if sub == 2 else "!! "
        print(f"{flag}{p.name:<28} Subsystem={sub}  {desc}")
        if sub != 2:
            bad += 1

    print()
    if bad:
        print(f"{bad} file(s) are not GUI subsystem: a console window may appear on launch")
        return 1
    print("All GUI subsystem: double-click / shortcut launch will NOT show a cmd window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
