"""启动打包好的 GUI，读取其状态栏文字后立即隐藏并关闭窗口。

用途：在没有人工点击的情况下，验证打包产物界面上的文字（例如版本号）是否正确。
用 Win32 的 EnumWindows / WM_GETTEXT 读取控件文本，全程不显示窗口内容。

用法：python tools/check-gui-statusbar.py <MediaConv.exe>
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

u32 = ctypes.windll.user32

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
SW_HIDE = 0

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def window_text(hwnd: int) -> str:
    n = u32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 2)
    u32.SendMessageW(hwnd, WM_GETTEXT, n + 1, buf)
    return buf.value


def child_texts(hwnd: int) -> list[tuple[str, str]]:
    """递归收集子窗口的 (类名, 文本)。"""
    out: list[tuple[str, str]] = []

    def cb(child, _lparam):
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(child, cls, 256)
        txt = window_text(child)
        if txt:
            out.append((cls.value, txt))
        child_texts(child)
        return True

    u32.EnumChildWindows(hwnd, EnumWindowsProc(cb), 0)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-gui-statusbar.py <MediaConv.exe>")
        return 2
    exe = sys.argv[1]

    proc = subprocess.Popen([exe])
    time.sleep(6)          # 等界面完成构建

    found: list[int] = []

    def top_cb(hwnd, _lparam):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == proc.pid:
            found.append(hwnd)
        return True

    u32.EnumWindows(EnumWindowsProc(top_cb), 0)

    if not found:
        print("未找到该进程的窗口（可能启动失败）")
        proc.kill()
        return 1

    hwnd = found[0]
    title = window_text(hwnd)
    print(f"窗口标题: {title}")

    items = child_texts(hwnd)
    print(f"子控件文本共 {len(items)} 条，其中包含状态栏信息的有：")
    keywords = ("版本", "发行者", "ffmpeg", "图片", "视频")
    hit = 0
    for cls, txt in items:
        if any(k in txt for k in keywords) and len(txt) > 8:
            print(f"  [{cls}] {txt}")
            hit += 1

    # 立刻隐藏并结束，避免打扰使用者
    u32.ShowWindow(hwnd, SW_HIDE)
    proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass

    print()
    if hit == 0:
        print("没有找到状态栏文字（可能界面还没画完）")
        return 1
    print("已读取到界面文字，窗口已关闭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
