"""对照实验：验证 GUI 子系统 exe 里 stdout 缓冲行为。

输出量大时缓冲区被填满自然会刷出（所以 info 正常），
输出量小时内容留在缓冲区里，若不显式 flush 就会丢失（所以 version 无输出）。

用法：python tools/check-stdout-flush.py <exe路径>
"""

from __future__ import annotations

import subprocess
import sys

TINY = "version"     # 只打印约 200 字节
BIG = "info"         # 打印数 KB


def run(exe: str, arg: str) -> tuple[int, int]:
    p = subprocess.run([exe, arg], capture_output=True, timeout=180)
    return len(p.stdout), len(p.stderr)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-stdout-flush.py <exe>")
        return 2
    exe = sys.argv[1]

    print(f"被测程序: {exe}\n")
    for label, arg in (("输出量小", TINY), ("输出量大", BIG)):
        out, err = run(exe, arg)
        verdict = "有输出" if out > 0 else "无输出  <- 缓冲区未刷新"
        print(f"  {label} ({arg:<8}) stdout={out:>6} 字节  stderr={err:>5} 字节   {verdict}")

    print()
    out_small, _ = run(exe, TINY)
    out_big, _ = run(exe, BIG)
    if out_small == 0 and out_big > 0:
        print("结论：确认是缓冲区未刷新的问题")
        return 1
    if out_small > 0:
        print("结论：两种输出量都正常")
        return 0
    print("结论：两种输出量都没有输出，问题不在缓冲")
    return 2


if __name__ == "__main__":
    sys.exit(main())
