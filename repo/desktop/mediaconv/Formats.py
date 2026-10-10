"""格式能力矩阵：在运行时探测本机 Pillow / FFmpeg 真实支持的格式。

设计原则：不硬编码"我以为支持的格式"，而是启动时向 Pillow 与 ffmpeg 询问实际能力，
这样打包换一个 ffmpeg 构建、或换一台电脑，列表都自动跟着变，不会出现"列了却转不了"。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Windows 下隐藏子进程控制台窗口
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _no_window_kwargs() -> dict:
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": _CREATE_NO_WINDOW}
    return {}


# --------------------------------------------------------------------------------------
# 图片格式
# --------------------------------------------------------------------------------------

# 提前注册可选图片插件。必须在任何 available_image_formats()/readable_image_exts()
# 调用之前完成，否则 Pillow 的 SAVE/OPEN 表里不会有 HEIC/AVIF，格式列表会残缺。
_PLUGIN_STATUS: dict[str, bool] = {"heif": False, "avif": False}


def register_image_plugins() -> dict[str, bool]:
    """注册 HEIC/HEIF 与 AVIF 读写支持（幂等，缺插件时静默跳过）。"""
    global _PLUGIN_STATUS
    if not _PLUGIN_STATUS["heif"]:
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
            _PLUGIN_STATUS["heif"] = True
        except Exception:
            pass
    if not _PLUGIN_STATUS["avif"]:
        for mod in ("pillow_avif", "pillow_avif_plugin"):
            try:
                __import__(mod)
                _PLUGIN_STATUS["avif"] = True
                break
            except Exception:
                continue
    return dict(_PLUGIN_STATUS)


register_image_plugins()


# 交给 Pillow 处理的扩展名（有这些扩展名就优先走图片通道）
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".jfi", ".png", ".apng", ".gif", ".bmp", ".dib",
    ".webp", ".tif", ".tiff", ".ico", ".tga", ".icns", ".ppm", ".pgm", ".pbm", ".pnm",
    ".pcx", ".dds", ".psd", ".eps", ".im", ".msp", ".sgi", ".spider", ".xbm", ".blp",
    ".cur", ".dcx", ".fli", ".flc", ".fpx", ".gbr", ".grib", ".hdr", ".icns", ".iim",
    ".j2c", ".j2k", ".jp2", ".jpc", ".jpf", ".jpx", ".mpo", ".mic", ".pcd", ".pfm",
    ".qoi", ".ras", ".rgb", ".rgba", ".bw", ".palm", ".wbm", ".wmf", ".emf", ".avif",
    ".heic", ".heif", ".hif", ".jp2", ".jxl", ".qoi",
}

# 视频/音频容器扩展名（走 ffmpeg 通道）
VIDEO_EXTS = {
    ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".qt", ".wmv", ".flv", ".f4v",
    ".swf", ".mpg", ".mpeg", ".mpe", ".m2v", ".ts", ".mts", ".m2ts", ".vob", ".3gp",
    ".3g2", ".ogv", ".ogg", ".rm", ".rmvb", ".asf", ".divx", ".xvid", ".mxf", ".dv",
    ".gifv", ".amv", ".drc", ".y4m", ".nut", ".roq", ".nsv", ".wtv", ".m3u8",
}

AUDIO_EXTS = {
    ".mp3", ".aac", ".m4a", ".m4b", ".wav", ".flac", ".ape", ".alac", ".ogg", ".oga",
    ".opus", ".wma", ".ac3", ".eac3", ".dts", ".mka", ".aiff", ".aif", ".aifc", ".amr",
    ".au", ".snd", ".caf", ".wv", ".tta", ".spx", ".ra", ".m4r", ".m3u",
}


def classify_ext(ext: str) -> str:
    """把扩展名归类为 image / video / audio / unknown。"""
    e = ext.lower()
    if e in IMAGE_EXTS and e not in {".gif"}:
        return "image"
    if e in VIDEO_EXTS:
        return "video"
    if e in AUDIO_EXTS:
        return "audio"
    if e == ".gif":
        return "image"  # GIF 既可能是动图也可能是单帧，统一交给图片通道
    if e in IMAGE_EXTS:
        return "image"
    return "unknown"


@dataclass(frozen=True)
class ImageFormat:
    """一个可写出的图片格式。"""

    key: str          # Pillow 内部格式名，如 "JPEG"
    ext: str          # 主扩展名，如 ".jpg"
    label: str        # 界面显示名
    supports_alpha: bool = False
    supports_multi: bool = False   # 支持多帧（动图）
    supports_quality: bool = True
    lossless: bool = False
    notes: str = ""


# Pillow 实际能力 + 我们的展示元数据。只有 Pillow 报告可保存的才会出现在界面里。
_IMAGE_META: dict[str, ImageFormat] = {
    "JPEG": ImageFormat("JPEG", ".jpg", "JPEG（.jpg）", False, False, True, False, "照片通用，体积小"),
    "PNG": ImageFormat("PNG", ".png", "PNG（.png）", True, False, True, True, "无损，支持透明"),
    "WEBP": ImageFormat("WEBP", ".webp", "WebP（.webp）", True, True, True, False, "体积比 JPEG 小 25%~35%"),
    "AVIF": ImageFormat("AVIF", ".avif", "AVIF（.avif）", True, False, True, False, "新一代格式，压缩率最高"),
    "HEIF": ImageFormat("HEIF", ".heic", "HEIC（.heic）", True, False, True, False, "iPhone 默认照片格式"),
    "BMP": ImageFormat("BMP", ".bmp", "BMP（.bmp）", False, False, False, True, "无压缩，体积大"),
    "GIF": ImageFormat("GIF", ".gif", "GIF（.gif）", True, True, False, True, "支持动图，最多 256 色"),
    "TIFF": ImageFormat("TIFF", ".tiff", "TIFF（.tiff）", True, True, True, True, "印刷/归档常用"),
    "ICO": ImageFormat("ICO", ".ico", "ICO（.ico）", True, False, False, True, "Windows 图标"),
    "ICNS": ImageFormat("ICNS", ".icns", "ICNS（.icns）", True, False, False, True, "macOS 图标"),
    "TGA": ImageFormat("TGA", ".tga", "TGA（.tga）", True, False, False, True, "游戏贴图"),
    "DDS": ImageFormat("DDS", ".dds", "DDS（.dds）", True, False, False, False, "DirectX 贴图"),
    "PCX": ImageFormat("PCX", ".pcx", "PCX（.pcx）", False, False, False, True, "老式格式"),
    "PPM": ImageFormat("PPM", ".ppm", "PPM（.ppm）", False, False, False, True, "无压缩中间格式"),
    "SGI": ImageFormat("SGI", ".sgi", "SGI（.sgi）", False, False, False, True, "SGI 图像"),
    "JPEG2000": ImageFormat("JPEG2000", ".jp2", "JPEG 2000（.jp2）", True, False, True, False, "医疗/档案"),
    "QOI": ImageFormat("QOI", ".qoi", "QOI（.qoi）", True, False, False, True, "极快无损"),
    "APNG": ImageFormat("PNG", ".apng", "APNG（.apng）", True, True, False, True, "动态 PNG"),
    "PDF": ImageFormat("PDF", ".pdf", "PDF（.pdf）", False, False, False, True, "图片转文档"),
    "MPO": ImageFormat("MPO", ".mpo", "MPO（.mpo）", False, True, True, False, "多图立体照片"),
    "PALM": ImageFormat("PALM", ".palm", "Palm（.palm）", False, False, True, False, "Palm 设备"),
    "WMF": ImageFormat("WMF", ".wmf", "WMF（.wmf）", False, False, False, True, "Windows 矢量"),
    "XBM": ImageFormat("XBM", ".xbm", "XBM（.xbm）", False, False, False, True, "X BitMap"),
}


@lru_cache(maxsize=1)
def _writable_pillow_formats() -> frozenset[str]:
    """返回 Pillow 真正能"写出"的格式名集合。

    关键点：Pillow 的格式插件是惰性导入的，未导入前 Image.SAVE 几乎是空的
    （实测只有被显式 import 过的插件才在里面）。Image.init() 会把所有已安装的
    插件都导入一遍，这样 SAVE / SAVE_ALL 才是完整可信的能力视图。
    """
    from PIL import Image

    try:
        Image.init()
    except Exception:
        pass
    fmts = {k.upper() for k in Image.SAVE.keys()} | {k.upper() for k in Image.SAVE_ALL.keys()}
    # registered_extensions 反映"插件已加载"，用它兜底一次交叉校验
    fmts |= {v.upper() for v in Image.registered_extensions().values()}
    return frozenset(fmts)


@lru_cache(maxsize=1)
def available_image_formats() -> list[ImageFormat]:
    """返回本机 Pillow 实际能写出的图片格式列表。"""
    writable = _writable_pillow_formats()

    out: list[ImageFormat] = []
    for key, meta in _IMAGE_META.items():
        pillow_key = "PNG" if key == "APNG" else key
        if pillow_key.upper() in writable:
            out.append(meta)
    # 按"常用程度"排序，把手机/电脑日常用的放前面
    order = ["JPEG", "PNG", "WEBP", "HEIF", "AVIF", "BMP", "GIF", "TIFF", "ICO", "PDF"]
    out.sort(key=lambda f: (order.index(f.key) if f.key in order else 99, f.key))
    return out


@lru_cache(maxsize=1)
def readable_image_exts() -> set[str]:
    """Pillow 实际能读的扩展名（含 HEIC/AVIF 插件注册的）。"""
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        import pillow_avif  # noqa: F401
    except Exception:
        pass
    return {e.lower() for e in Image.registered_extensions()}


# --------------------------------------------------------------------------------------
# FFmpeg 能力
# --------------------------------------------------------------------------------------


@dataclass
class FFmpegCaps:
    """一次探测得到的 ffmpeg 能力快照。"""

    version: str = ""
    muxers: set[str] = field(default_factory=set)      # 能输出的容器
    encoders: dict[str, str] = field(default_factory=dict)  # 编码器名 -> 类型(V/A/S)
    demuxers: set[str] = field(default_factory=set)
    decoders: set[str] = field(default_factory=set)
    filters: set[str] = field(default_factory=set)
    hwaccels: set[str] = field(default_factory=set)
    raw: str = ""

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def video_encoders(self) -> list[str]:
        return sorted(n for n, t in self.encoders.items() if t == "V")

    def audio_encoders(self) -> list[str]:
        return sorted(n for n, t in self.encoders.items() if t == "A")


def run_ffmpeg_tool(exe: str, args: list[str], timeout: int = 60) -> str:
    """运行 ffmpeg/ffprobe 并返回 stdout 文本。"""
    proc = subprocess.run(
        [exe, *args],
        capture_output=True,
        timeout=timeout,
        **_no_window_kwargs(),
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    return out + ("\n" + err if err and not out else "")


def probe_ffmpeg(ffmpeg_path: Path) -> FFmpegCaps:
    """探测 ffmpeg 的容器/编码器/滤镜能力。失败时返回空能力（界面会提示）。"""
    caps = FFmpegCaps()
    if not ffmpeg_path or not Path(ffmpeg_path).exists():
        return caps

    try:
        banner = run_ffmpeg_tool(str(ffmpeg_path), ["-hide_banner", "-version"], timeout=30)
        m = re.search(r"ffmpeg version (\S+)", banner)
        caps.version = m.group(1) if m else "unknown"
    except Exception:
        return caps

    def collect(args: list[str], pattern: str) -> set[str]:
        try:
            text = run_ffmpeg_tool(str(ffmpeg_path), ["-hide_banner", *args], timeout=90)
        except Exception:
            return set()
        found = set()
        for line in text.splitlines():
            mm = re.match(pattern, line)
            if mm:
                found.add(mm.group(2))
        return found

    caps.muxers = collect(["-muxers"], r"^\s*([ .]?E)\s+(\S+)")
    caps.demuxers = collect(["-demuxers"], r"^\s*([ .]?D)\s+(\S+)")
    caps.decoders = collect(["-decoders"], r"^\s*([ .]?[VAS])[.A-Z]*\s+(\S+)")
    caps.filters = collect(["-filters"], r"^\s*\S+\s+(\S+)\s+->\s+\S+")

    # 编码器需要区分音频/视频类型
    try:
        text = run_ffmpeg_tool(str(ffmpeg_path), ["-hide_banner", "-encoders"], timeout=90)
        for line in text.splitlines():
            mm = re.match(r"^\s*([VAS])[.A-Z]*\s+(\S+)", line)
            if mm:
                caps.encoders[mm.group(2)] = mm.group(1)
    except Exception:
        pass

    try:
        text = run_ffmpeg_tool(str(ffmpeg_path), ["-hide_banner", "-hwaccels"], timeout=60)
        for line in text.splitlines():
            line = line.strip()
            if line and not line.lower().startswith(("hardware", "hwaccel")):
                caps.hwaccels.add(line)
    except Exception:
        pass

    return caps


@dataclass(frozen=True)
class VideoFormat:
    """一个可输出的视频/音频容器。"""

    key: str            # 界面标识
    ext: str            # 扩展名
    label: str
    muxer: str          # ffmpeg -f 参数
    vcodec: str         # 默认视频编码器
    acodec: str         # 默认音频编码器
    kind: str = "video"  # video / audio
    notes: str = ""
    container_args: tuple[str, ...] = ()   # 额外的容器参数（如 faststart）


# 常见目标格式。实际是否显示由 ffmpeg 探针决定。
VIDEO_TARGETS: list[VideoFormat] = [
    VideoFormat("mp4_h264", ".mp4", "MP4 / H.264（兼容性最好）", "mp4", "libx264", "aac",
                notes="手机、微信、剪辑软件通吃", container_args=("-movflags", "+faststart")),
    VideoFormat("mp4_h265", ".mp4", "MP4 / H.265（体积更小）", "mp4", "libx265", "aac",
                notes="同画质体积约小 40%，老设备可能不支持"),
    VideoFormat("mkv_h264", ".mkv", "MKV / H.264", "matroska", "libx264", "aac",
                notes="封装能力最强，可容纳多音轨字幕"),
    VideoFormat("mkv_h265", ".mkv", "MKV / H.265", "matroska", "libx265", "aac"),
    VideoFormat("webm_vp9", ".webm", "WebM / VP9", "webm", "libvpx-vp9", "libopus",
                notes="网页友好，开源免专利"),
    VideoFormat("webm_vp8", ".webm", "WebM / VP8", "webm", "libvpx", "libvorbis"),
    VideoFormat("webm_av1", ".webm", "WebM / AV1", "webm", "libaom-av1", "libopus",
                notes="压缩率最高，编码很慢"),
    VideoFormat("mov_h264", ".mov", "MOV / H.264", "mov", "libx264", "aac",
                notes="苹果生态常用"),
    VideoFormat("mov_prores", ".mov", "MOV / ProRes（剪辑用）", "mov", "prores_ks", "pcm_s16le",
                notes="专业剪辑中间格式，体积很大"),
    VideoFormat("avi_mpeg4", ".avi", "AVI / MPEG-4", "avi", "mpeg4", "libmp3lame",
                notes="老设备/老播放器兼容"),
    VideoFormat("avi_mjpeg", ".avi", "AVI / MJPEG", "avi", "mjpeg", "pcm_s16le"),
    VideoFormat("ts_h264", ".ts", "MPEG-TS / H.264", "mpegts", "libx264", "aac",
                notes="电视广播/直播流"),
    VideoFormat("flv_h264", ".flv", "FLV / H.264", "flv", "libx264", "aac",
                notes="老式网页视频"),
    VideoFormat("wmv2", ".wmv", "WMV / WMV2", "asf", "wmv2", "wmav2",
                notes="Windows Media"),
    VideoFormat("ogv", ".ogv", "OGG / Theora", "ogg", "libtheora", "libvorbis"),
    VideoFormat("3gp", ".3gp", "3GP（老手机）", "3gp", "libx264", "aac"),
    VideoFormat("mpeg2", ".mpg", "MPEG-2 / DVD", "mpeg", "mpeg2video", "mp2",
                notes="DVD、老式播放设备"),
    VideoFormat("gif_anim", ".gif", "GIF 动图", "gif", "gif", "none",
                notes="自动生成调色板，适合表情包"),
    VideoFormat("webp_anim", ".webp", "WebP 动图", "webp", "libwebp_anim", "none"),
    VideoFormat("apng_anim", ".apng", "APNG 动图", "apng", "apng", "none"),
    VideoFormat("mp3", ".mp3", "MP3 音频", "mp3", "none", "libmp3lame", kind="audio",
                notes="提取音轨，兼容性最好"),
    VideoFormat("m4a", ".m4a", "M4A / AAC 音频", "ipod", "none", "aac", kind="audio"),
    VideoFormat("aac", ".aac", "AAC 音频", "adts", "none", "aac", kind="audio"),
    VideoFormat("wav", ".wav", "WAV 无损音频", "wav", "none", "pcm_s16le", kind="audio"),
    VideoFormat("flac", ".flac", "FLAC 无损音频", "flac", "none", "flac", kind="audio"),
    VideoFormat("opus", ".opus", "Opus 音频", "opus", "none", "libopus", kind="audio"),
    VideoFormat("ogg_audio", ".ogg", "OGG / Vorbis 音频", "ogg", "none", "libvorbis", kind="audio"),
    VideoFormat("wma", ".wma", "WMA 音频", "asf", "none", "wmav2", kind="audio"),
    VideoFormat("ac3", ".ac3", "AC3 音频", "ac3", "none", "ac3", kind="audio"),
    VideoFormat("amr", ".amr", "AMR 音频（手机录音）", "amr", "none", "libopencore_amrnb", kind="audio"),
    VideoFormat("m4r", ".m4r", "M4R 铃声（iPhone）", "ipod", "none", "aac", kind="audio"),
    VideoFormat("aiff", ".aiff", "AIFF 无损音频", "aiff", "none", "pcm_s16be", kind="audio"),
]


def available_video_targets(caps: FFmpegCaps) -> list[VideoFormat]:
    """按 ffmpeg 实际能力过滤目标格式列表。"""
    out: list[VideoFormat] = []
    for t in VIDEO_TARGETS:
        if t.muxer not in caps.muxers:
            continue
        if t.vcodec != "none" and not caps.has_encoder(t.vcodec):
            continue
        if t.acodec != "none" and not caps.has_encoder(t.acodec):
            continue
        out.append(t)
    return out


def summary() -> str:
    """生成一份能力摘要，便于自检与排错。"""
    caps_img = available_image_formats()
    return json.dumps(
        {
            "image_formats": [f.ext for f in caps_img],
            "image_ext_count": len(readable_image_exts()),
        },
        ensure_ascii=False,
        indent=2,
    )
