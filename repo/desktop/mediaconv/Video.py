"""视频 / 音频转换引擎：在 ffmpeg 之上构建参数化转码。

设计要点：
  * 面向"能转市面上常见的格式"，所以容器与编码器都由能力矩阵动态提供；
  * 默认针对手机/网页播放做兼容性处理（yuv420p、faststart、AAC）；
  * 支持"仅换容器不重编码"的极速模式。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import FFmpeg, Formats


class VideoConvertError(RuntimeError):
    pass


# 质量档位 -> CRF（x264/x265/VP9 等 CRF 型编码器）
CRF_PRESETS = {
    "high": 18,        # 高画质
    "balanced": 23,    # 均衡（默认）
    "small": 28,       # 小体积
    "tiny": 32,        # 极小体积
}

# 质量档位 -> 目标码率（kbps/每千像素），用于不支持 CRF 的编码器
BITRATE_PRESETS = {"high": 14, "balanced": 8, "small": 5, "tiny": 3}


@dataclass
class VideoOptions:
    """视频转换参数。"""

    target_key: str = "mp4_h264"
    quality: str = "balanced"          # high / balanced / small / tiny
    crf_override: int | None = None    # 直接指定 CRF
    scale: str = "keep"                # keep | 2160 | 1440 | 1080 | 720 | 480 | 360
    fps: float = 0.0                   # 0 表示保持原始帧率
    audio_mode: str = "encode"         # keep | encode | none
    audio_bitrate: str = "192k"
    copy_streams: bool = False         # 仅换容器（不重编码）
    pix_fmt: str = "yuv420p"           # 兼容性优先
    trim_start: float = 0.0            # 起始时间（秒）
    trim_end: float = 0.0              # 结束时间（秒），0 表示到结尾
    faststart: bool = True
    two_pass: bool = False
    extra_args: list[str] = field(default_factory=list)


@dataclass
class VideoConvertResult:
    output: Path
    in_size: int = 0
    out_size: int = 0
    duration: float = 0.0
    log_tail: str = ""

    @property
    def ratio_text(self) -> str:
        if not self.in_size or not self.out_size:
            return ""
        return f"{(self.out_size - self.in_size) / self.in_size * 100:+.1f}%"


def _target(key: str) -> Formats.VideoFormat:
    caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
    for t in Formats.available_video_targets(caps):
        if t.key == key:
            return t
    for t in Formats.VIDEO_TARGETS:
        if t.key == key:
            return t
    raise VideoConvertError(f"未知目标格式：{key}")


def _scale_filter(scale: str, target: Formats.VideoFormat) -> list[str]:
    """生成缩放滤镜参数。"""
    if scale == "keep" or not scale:
        return []
    try:
        height = int(scale)
    except ValueError:
        return []
    # 等比缩放到指定高度，宽度取偶数（H.264 要求）
    return ["-vf", f"scale=-2:{height}:flags=lanczos"]


def _quality_args(codec: str, opt: VideoOptions, width: int, height: int) -> list[str]:
    """按编码器类型生成质量控制参数。"""
    crf = opt.crf_override if opt.crf_override is not None else CRF_PRESETS.get(opt.quality, 23)
    args: list[str] = []

    if codec in ("libx264", "libx265"):
        args += ["-crf", str(crf)]
        # 速度与体积的平衡：medium 更适合桌面 CPU 上的默认体验
        args += ["-preset", "medium"]
        if codec == "libx265":
            args += ["-tag:v", "hvc1"]  # 让 QuickTime/苹果设备识别
    elif codec in ("libvpx", "libvpx-vp9"):
        # VPx 用 -crf + -b:v 0 才是恒定质量模式
        vp_crf = max(4, min(63, crf + 8))
        args += ["-crf", str(vp_crf), "-b:v", "0"]
        if codec == "libvpx-vp9":
            args += ["-row-mt", "1", "-cpu-used", "2", "-deadline", "good"]
    elif codec in ("libaom-av1", "libsvtav1"):
        av1_crf = max(0, min(63, crf + 5))
        args += ["-crf", str(av1_crf), "-b:v", "0"]
        if codec == "libaom-av1":
            args += ["-cpu-used", "6", "-row-mt", "1"]
    elif codec in ("mpeg4", "msmpeg4v3", "wmv2", "mpeg2video", "mjpeg", "libtheora", "h263"):
        # 老编码器用码率控制
        kbps = BITRATE_PRESETS.get(opt.quality, 8) * max(1, (width * height) // 1000)
        args += ["-b:v", f"{int(kbps)}k"]
    elif codec == "prores_ks":
        profile = {"high": "3", "balanced": "2", "small": "1", "tiny": "0"}.get(opt.quality, "2")
        args += ["-profile:v", profile]
    elif codec in ("gif", "apng"):
        pass  # 动图格式不用质量控制
    return args


def _audio_args(target: Formats.VideoFormat, opt: VideoOptions, caps: Formats.FFmpegCaps) -> list[str]:
    """音频轨参数。

    易错点：音频专用容器需要 "-vn"（丢掉视频轨）而不是 "-an"。
    如果两者同时出现，ffmpeg 会认为没有任何流要输出，
    报错 "Error opening output files: Invalid argument"。
    """
    # 目标本身就是音频格式：丢掉视频轨，按目标编码器编码音频
    if target.kind == "audio":
        args = ["-vn"]
        acodec = target.acodec
        if acodec == "none":
            return args + ["-an"]
        args += ["-c:a", acodec]
        if acodec not in ("flac", "pcm_s16le", "pcm_s16be", "pcm_s24le", "alac"):
            args += ["-b:a", opt.audio_bitrate]
        if acodec in ("aac", "libopus", "libvorbis", "libmp3lame", "ac3", "wmav2", "libopencore_amrnb"):
            args += ["-ac", "1" if acodec == "libopencore_amrnb" else "2"]
        if acodec == "libopencore_amrnb":
            args += ["-ar", "8000"]
        return args

    # 视频容器：按用户选择决定是否保留音频
    if opt.audio_mode == "none" or target.acodec == "none":
        return ["-an"]
    acodec = target.acodec
    args = ["-c:a", acodec]
    if acodec not in ("flac", "pcm_s16le", "pcm_s16be", "pcm_s24le", "alac"):
        args += ["-b:a", opt.audio_bitrate]
    if acodec in ("aac", "libopus", "libvorbis"):
        args += ["-ac", "2"]
    return args


def build_args(src: Path, dst: Path, opt: VideoOptions, info: FFmpeg.MediaInfo,
               caps: Formats.FFmpegCaps) -> list[str]:
    """构造 ffmpeg 参数列表。"""
    target = _target(opt.target_key)
    args: list[str] = []

    # 裁剪
    if opt.trim_start > 0:
        args += ["-ss", f"{opt.trim_start:.3f}"]
    if opt.trim_end > 0 and opt.trim_end > opt.trim_start:
        args += ["-to", f"{opt.trim_end:.3f}"]

    args += ["-i", str(src)]

    # 极速模式：直接复制流（仅在容器兼容时可用）
    if opt.copy_streams:
        args += ["-c", "copy"]
        if target.kind == "audio":
            args += ["-vn"]
        args += _container_args(target, opt)
        args += ["-f", target.muxer, str(dst)]
        return args

    # 视频编码参数
    if target.kind == "video" and info.has_video:
        args += ["-c:v", target.vcodec]
        args += _scale_filter(opt.scale, target)
        if opt.fps and opt.fps > 0:
            args += ["-r", f"{opt.fps:g}"]
        w = info.width or 1920
        h = info.height or 1080
        if opt.scale not in ("keep", "") and str(opt.scale).isdigit():
            ratio = int(opt.scale) / (h or 1)
            w, h = int(w * ratio), int(opt.scale)
        args += _quality_args(target.vcodec, opt, w, h)

        if target.vcodec not in ("gif", "apng"):
            if opt.pix_fmt:
                args += ["-pix_fmt", opt.pix_fmt]

    # 音频轨参数（音频专用容器与视频容器分别处理，见 _audio_args）
    args += _audio_args(target, opt, caps)

    args += _container_args(target, opt)
    args += opt.extra_args
    args += ["-f", target.muxer, str(dst)]
    return args


def _container_args(target: Formats.VideoFormat, opt: VideoOptions) -> list[str]:
    """容器级参数。

    注意：-movflags 只对 mov/mp4/ipod 系列有意义，若误加到 mp3 等容器上，
    ffmpeg 会直接报 "Error opening output file ... Invalid argument"。
    """
    args: list[str] = []

    if target.muxer in ("mp4", "mov", "ipod"):
        if opt.faststart and not opt.copy_streams:
            args += ["-movflags", "+faststart"]

    if target.key == "gif_anim":
        args += ["-loop", "0"]

    # 老式 AVI 需要放宽标准校验，否则部分编码（如 mpeg4+aac）会被拒绝
    if target.muxer == "avi":
        args += ["-strict", "-2"]

    return args


def convert_video(
    src: str | Path,
    dst: str | Path,
    opt: VideoOptions,
    *,
    on_progress=None,
    on_log=None,
    cancel_check=None,
) -> VideoConvertResult:
    """执行视频/音频转换。"""
    src_p, dst_p = Path(src), Path(dst)
    if not src_p.exists():
        raise VideoConvertError(f"文件不存在：{src_p}")
    if FFmpeg.ffmpeg_path() is None:
        raise FFmpeg.FFmpegNotFound("未找到 ffmpeg")

    caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path())
    info = FFmpeg.probe(src_p)
    dst_p.parent.mkdir(parents=True, exist_ok=True)

    # 提前检查流是否匹配目标需求。
    # 不做这一步的话，给"没有音轨的视频"提取音轨会得到 ffmpeg 的
    # "Error opening output files: Invalid argument" —— 用户完全看不懂。
    target = _target(opt.target_key)
    if not info.has_video and not info.has_audio:
        raise VideoConvertError(
            f"这个文件里没有找到可用的音视频轨，无法转换：{src_p.name}\n"
            "（可能不是媒体文件，或文件已损坏）"
        )
    if target.kind == "audio" and not info.has_audio:
        raise VideoConvertError(
            f"这个文件没有音轨，无法提取音频：{src_p.name}\n"
            "如果它是视频，请选择一个视频格式（如 MP4 / H.264）来转换。"
        )
    if target.kind == "video" and not info.has_video:
        raise VideoConvertError(
            f"这个文件没有视频轨，无法转成视频：{src_p.name}\n"
            "如果它是音频文件，请选择音频格式（如 MP3 / M4A / WAV）。"
        )

    duration = info.duration
    if opt.trim_end > 0 and opt.trim_end > opt.trim_start:
        duration = min(duration, opt.trim_end) - opt.trim_start if duration else 0
    elif opt.trim_start > 0 and duration:
        duration = max(0.0, duration - opt.trim_start)

    args = build_args(src_p, dst_p, opt, info, caps)
    code, log = FFmpeg.run_ffmpeg(
        args,
        duration=duration,
        on_progress=on_progress,
        on_log=on_log,
        cancel_check=cancel_check,
    )

    if code != 0 or not dst_p.exists() or dst_p.stat().st_size == 0:
        msg = FFmpeg.summarize_error(log)
        # 给出更贴近用户的建议
        hint = ""
        if "Unknown encoder" in log:
            hint = "\n提示：当前 ffmpeg 未编译该编码器，请换一个目标格式，或使用完整版 ffmpeg。"
        elif "not supported" in log.lower() or "could not find tag" in log.lower():
            hint = "\n提示：该容器不支持所选编码，试试换成 MP4/MKV 这类通用容器。"
        raise VideoConvertError(f"转换失败：\n{msg}{hint}")

    res = VideoConvertResult(
        output=dst_p,
        in_size=src_p.stat().st_size,
        out_size=dst_p.stat().st_size,
        duration=duration,
        log_tail="\n".join(log.splitlines()[-5:]),
    )
    return res


def extraction_command_preview(src: str | Path, dst: str | Path, opt: VideoOptions) -> str:
    """给用户看实际执行的 ffmpeg 命令（排错/进阶用）。"""
    try:
        caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
        info = FFmpeg.probe(src)
        args = build_args(Path(src), Path(dst), opt, info, caps)
        return "ffmpeg " + " ".join(f'"{a}"' if " " in a else a for a in args)
    except Exception as e:
        return f"（无法生成命令预览：{e}）"


def suggest_output(src: str | Path, target_key: str, out_dir: str | Path | None = None,
                   suffix: str = "_converted") -> Path:
    target = _target(target_key)
    src_p = Path(src)
    directory = Path(out_dir) if out_dir else src_p.parent
    candidate = directory / f"{src_p.stem}{suffix}{target.ext}"
    n = 1
    while candidate.exists() and candidate.resolve() != src_p.resolve():
        candidate = directory / f"{src_p.stem}{suffix}_{n}{target.ext}"
        n += 1
    if candidate.resolve() == src_p.resolve():
        candidate = directory / f"{src_p.stem}{suffix}_out{target.ext}"
    return candidate
