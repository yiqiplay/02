"""MediaConv 统一入口：无参数启动图形界面，带参数走命令行。

打包成 GUI 子系统 exe（console=False）后，Windows 不会在启动时创建控制台窗口，
所以双击 / 快捷方式启动时不会闪黑框。代价是命令行模式默认没有输出设备，
需要在启动时主动接上父进程的控制台（见 _attach_parent_console）。
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"


def _attach_parent_console() -> bool:
    """命令行模式下把自己接到父进程的控制台，让 print 能被看到。

    GUI 子系统 exe 没有自带控制台，这里要做两件事：
      1. AttachConsole 接上父进程（cmd / PowerShell）的控制台；
      2. 重建 sys.stdout / stderr / stdin。

    第 2 步有个关键取舍：如果父进程是用管道捕获输出的（例如
    `MediaConv.exe info | more`、在脚本里重定向到文件），那么必须**复用继承来的
    标准句柄**，直接打开 CONOUT$ 会把内容写进控制台而绕过管道，结果是调用方
    什么都收不到。只有确实没有可用句柄时才回退到 CONOUT$ / CONIN$。
    """
    if not IS_WIN:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        ATTACH_PARENT_PROCESS = -1
        STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE = -10, -11, -12
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        k32 = ctypes.windll.kernel32
        attached = bool(k32.AttachConsole(ATTACH_PARENT_PROCESS))

        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetStdHandle.argtypes = [wintypes.DWORD]

        def inherited_handle(std_id: int):
            h = k32.GetStdHandle(std_id)
            if h is None or h == INVALID_HANDLE_VALUE or h == 0:
                return None
            return h

        def wrap(handle, name: str):
            """用 CRT 的 _open_osfhandle 把 Win32 句柄变成 C 运行时 fd。"""
            import msvcrt

            # _open_osfhandle 的 flag：0 表示按原样接管，不做文本转换
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY if name == "stdin" else os.O_WRONLY)
            if name == "stdin":
                return io.TextIOWrapper(io.open(fd, "rb", closefd=True),
                                        encoding="utf-8", errors="replace")
            # 注意：二进制模式下不能用 line_buffering / buffering=1（会告警），
            # 输出模式由 write_through 保证及时刷出。
            return io.TextIOWrapper(io.open(fd, "wb", closefd=True),
                                    encoding="utf-8", errors="replace", write_through=True)

        got_any = False
        for name, std_id, dev in (
            ("stdout", STD_OUTPUT_HANDLE, "CONOUT$"),
            ("stderr", STD_ERROR_HANDLE, "CONOUT$"),
            ("stdin", STD_INPUT_HANDLE, "CONIN$"),
        ):
            # 已经在用的流就不动它，避免打断调用方的重定向
            if getattr(sys, name, None) is not None:
                continue

            handle = inherited_handle(std_id)
            if handle is not None:
                try:
                    setattr(sys, name, wrap(handle, name))
                    got_any = True
                    continue
                except Exception:
                    pass

            # 回退：直接打开控制台设备
            try:
                setattr(sys, name, open(dev, "rb" if name == "stdin" else "w",
                                        encoding=None, buffering=0 if name == "stdin" else -1))
                got_any = True
            except Exception:
                setattr(sys, name, open(os.devnull, "rb" if name == "stdin" else "w"))

        return attached or got_any
    except Exception:
        return False


def _fix_console_encoding() -> None:
    """Windows 默认控制台是 GBK，中文与特殊符号会乱码/报错。"""
    if not IS_WIN:
        return
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            elif hasattr(stream, "buffer"):
                setattr(sys, stream_name,
                        io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"))
        except Exception:
            pass


def _hide_console_window() -> None:
    """兜底：万一仍有控制台窗口（例如被系统分配），直接隐藏。

    正常情况下 GUI 子系统 exe 不会有控制台，这里只是双保险。
    """
    if not IS_WIN:
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _has_cli_args(argv: list[str]) -> bool:
    """判断这次启动是不是命令行模式。

    只有"看起来像命令"的参数才算，避免把资源管理器拖拽产生的文件路径
    误判成命令行调用（那种情况应该开图形界面）。
    """
    if not argv:
        return False
    known = {"info", "list", "convert", "version", "-h", "--help", "-V", "--version"}
    first = argv[0].lower()
    if first in known:
        return True
    # 未知子命令（拼错的情况）也走命令行，好让 argparse 报错提示
    return not (first.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".avif",
                                ".bmp", ".gif", ".tif", ".tiff", ".mp4", ".mkv",
                                ".webm", ".avi", ".mov", ".mp3", ".wav", ".flac")) or os.path.exists(argv[0]))


def main() -> int:
    argv = sys.argv[1:]
    cli_mode = _has_cli_args(argv)

    if cli_mode:
        # 命令行模式：接上父控制台，否则用户看不到任何输出
        _attach_parent_console()
        _fix_console_encoding()

    # 让源码目录与打包目录都能 import mediaconv
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent):
        if (candidate / "mediaconv").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    if not cli_mode:
        # 图形界面模式：确保没有任何控制台窗口残留
        _hide_console_window()
        try:
            from mediaconv.Gui import run_gui

            return run_gui()
        except ImportError as e:
            _attach_parent_console()
            _fix_console_encoding()
            print(f"图形界面需要 PySide6：{e}")
            print("可用命令行模式：MediaConv.exe info")
            return 1

    from mediaconv.Cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
