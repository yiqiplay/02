"""FFmpeg / ffprobe 定位与调用封装。

查找顺序（先打包内置、后系统安装）：
  1. 程序自带的 bin 目录（打包后随程序分发，保证开箱即用）
  2. 环境变量 MEDIACONV_FFMPEG / MEDIACONV_FFPROBE
  3. 系统 PATH
  4. Windows 上常见的安装位置
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _no_window_kwargs() -> dict:
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": _CREATE_NO_WINDOW}
    return {}


def app_dir() -> Path:
    """程序所在目录（打包后是 exe 所在目录，开发时是项目根）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """只读资源目录（PyInstaller 解包目录 _MEIPASS）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


def _candidate_dirs() -> list[Path]:
    dirs = [
        app_dir() / "bin",            # 免安装版：exe 同级 bin/
        app_dir() / "ffmpeg" / "bin",
        resource_dir() / "bin",       # 单文件版解包目录
        resource_dir() / "ffmpeg" / "bin",
    ]
    return [d for d in dirs if d.is_dir()]


def _find_tool(name: str, env_var: str) -> Path | None:
    exe = f"{name}.exe" if sys.platform == "win32" else name
    env = os.environ.get(env_var)
    if env and Path(env).exists():
        return Path(env).resolve()
    for d in _candidate_dirs():
        p = d / exe
        if p.exists():
            return p
    found = shutil.which(name)
    if found:
        return Path(found)
    if sys.platform == "win32":
        for base in (
            Path(r"C:\ffmpeg\bin"),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
        ):
            p = base / exe
            if p.exists():
                return p
    return None


_FFMPEG: Path | None = None
_FFPROBE: Path | None = None
_FFMPEG_RESOLVED = False


def ffmpeg_path() -> Path | None:
    global _FFMPEG, _FFMPEG_RESOLVED
    if not _FFMPEG_RESOLVED:
        _FFMPEG = _find_tool("ffmpeg", "MEDIACONV_FFMPEG")
        _FFMPEG_RESOLVED = True
    return _FFMPEG


def ffprobe_path() -> Path | None:
    global _FFPROBE
    if _FFPROBE is None:
        _FFPROBE = _find_tool("ffprobe", "MEDIACONV_FFPROBE")
        if _FFPROBE is None:
            ff = ffmpeg_path()
            if ff is not None:
                cand = ff.with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
                if cand.exists():
                    _FFPROBE = cand
    return _FFPROBE


class FFmpegNotFound(RuntimeError):
    pass


@dataclass
class MediaInfo:
    """ffprobe 探测到的媒体信息。"""

    path: Path
    format_name: str = ""
    duration: float = 0.0
    size: int = 0
    bit_rate: int = 0
    width: int = 0
    height: int = 0
    vcodec: str = ""
    acodec: str = ""
    fps: float = 0.0
    has_video: bool = False
    has_audio: bool = False
    streams: int = 0
    raw: dict | None = None

    @property
    def kind(self) -> str:
        if self.has_video:
            return "video"
        if self.has_audio:
            return "audio"
        return "unknown"

    def describe(self) -> str:
        bits = []
        if self.has_video:
            res = f"{self.width}x{self.height}" if self.width else "?"
            bits.append(f"{self.vcodec or 'video'} {res}")
            if self.fps:
                bits.append(f"{self.fps:g}fps")
        if self.has_audio:
            bits.append(self.acodec or "audio")
        if self.duration:
            bits.append(format_duration(self.duration))
        return " · ".join(bits) if bits else (self.format_name or "未知")


def format_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return ""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def probe(path: str | Path, timeout: int = 60) -> MediaInfo:
    """用 ffprobe 读取媒体信息；失败时返回仅含路径的空信息。"""
    p = Path(path)
    info = MediaInfo(path=p)
    try:
        info.size = p.stat().st_size
    except OSError:
        pass

    exe = ffprobe_path()
    if exe is None:
        return info

    cmd = [
        str(exe), "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(p),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, **_no_window_kwargs())
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except Exception:
        return info

    info.raw = data
    fmt = data.get("format", {}) or {}
    info.format_name = (fmt.get("format_name") or "").split(",")[0]
    try:
        info.duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        info.duration = 0.0
    try:
        info.bit_rate = int(fmt.get("bit_rate") or 0)
    except (TypeError, ValueError):
        info.bit_rate = 0

    streams = data.get("streams", []) or []
    info.streams = len(streams)
    for st in streams:
        ctype = st.get("codec_type")
        if ctype == "video":
            if st.get("disposition", {}).get("attached_pic"):
                continue  # 封面图不算视频轨
            info.has_video = True
            info.vcodec = st.get("codec_name") or ""
            info.width = int(st.get("width") or 0)
            info.height = int(st.get("height") or 0)
            info.fps = _parse_fps(st.get("avg_frame_rate") or st.get("r_frame_rate") or "")
            if not info.duration:
                try:
                    info.duration = float(st.get("duration") or 0)
                except (TypeError, ValueError):
                    pass
        elif ctype == "audio" and not info.has_audio:
            info.has_audio = True
            info.acodec = st.get("codec_name") or ""
    return info


def _parse_fps(text: str) -> float:
    if not text or text == "0/0":
        return 0.0
    if "/" in text:
        num, _, den = text.partition("/")
        try:
            d = float(den)
            return float(num) / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
_SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")


def run_ffmpeg(
    args: list[str],
    *,
    duration: float = 0.0,
    on_progress=None,
    on_log=None,
    cancel_check=None,
    timeout: int | None = None,
) -> tuple[int, str]:
    """运行 ffmpeg 并实时解析进度。

    参数:
      args: 传给 ffmpeg 的参数（不含可执行文件本身），会自动加 -hide_banner -y
      duration: 总时长，用于计算百分比
      on_progress: 回调 (progress_0_to_1, speed_text, out_time_seconds)
      on_log: 回调 (日志行)
      cancel_check: 返回 True 时中断转换
    返回 (returncode, 完整日志)
    """
    exe = ffmpeg_path()
    if exe is None:
        raise FFmpegNotFound("未找到 ffmpeg，请将其放入程序目录的 bin 文件夹，或设置 MEDIACONV_FFMPEG 环境变量")

    cmd = [str(exe), "-hide_banner", "-y", "-nostdin", *args]

    stderr_chunks: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        bufsize=1,
        universal_newlines=False,
        **_no_window_kwargs(),
    )

    assert proc.stderr is not None
    try:
        for raw in iter(proc.stderr.readline, b""):
            if cancel_check is not None and cancel_check():
                proc.kill()
                stderr_chunks.append("\n[cancelled by user]")
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                continue
            stderr_chunks.append(line)
            if on_log is not None:
                on_log(line)
            if on_progress is not None:
                m = _TIME_RE.search(line)
                if m:
                    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    out_time = h * 3600 + mi * 60 + s
                    frac = min(1.0, out_time / duration) if duration > 0 else 0.0
                    sp = _SPEED_RE.search(line)
                    on_progress(frac, sp.group(1) + "x" if sp else "", out_time)
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        code = proc.wait()

    log = "\n".join(stderr_chunks)
    if on_progress is not None and code == 0:
        on_progress(1.0, "", duration)
    return code, log


def run_capture(args: list[str], timeout: int = 120) -> tuple[int, str]:
    """运行 ffmpeg 并返回完整输出（用于探测类小任务）。"""
    exe = ffmpeg_path()
    if exe is None:
        raise FFmpegNotFound("未找到 ffmpeg")
    proc = subprocess.run(
        [str(exe), "-hide_banner", "-nostdin", *args],
        capture_output=True,
        timeout=timeout,
        **_no_window_kwargs(),
    )
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


def summarize_error(log: str, max_lines: int = 6) -> str:
    """从 ffmpeg 日志里提炼出有用的错误信息。"""
    if not log:
        return "未知错误"
    lines = [ln.strip() for ln in log.splitlines() if ln.strip()]
    interesting = [
        ln for ln in lines
        if re.search(r"error|invalid|failed|unable|not found|unsupported|no such|denied|Invalid argument", ln, re.I)
        and not ln.startswith(("frame=", "size=", "video:", "Stream mapping", "Press ["))
    ]
    picked = interesting[-max_lines:] if interesting else lines[-max_lines:]
    return "\n".join(picked)
