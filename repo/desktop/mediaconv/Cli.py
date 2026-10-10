"""命令行界面：既能被 GUI 同款引擎驱动，也能在批处理/服务器场景直接调用。

用法示例：
    MediaConv.exe info                                 查看本机支持的格式
    MediaConv.exe convert a.mp4 -t webm_vp9 -q small   单个文件转换
    MediaConv.exe convert *.png -t WEBP -q 85          批量转换
    MediaConv.exe convert in.mov -t gif_anim --scale 480 --fps 12
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from . import FFmpeg, Formats, Images, Video

PROG = "MediaConv"


def _collect_inputs(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in patterns:
        path = Path(p)
        if path.is_file():
            out.append(path)
            continue
        # Windows 下用户可能直接写通配符
        matches = [Path(m) for m in glob.glob(p, recursive=True)]
        matches = [m for m in matches if m.is_file()]
        if matches:
            out.extend(sorted(matches))
        elif path.is_dir():
            for child in sorted(path.iterdir()):
                if child.is_file() and (
                    child.suffix.lower() in Formats.IMAGE_EXTS
                    or child.suffix.lower() in Formats.VIDEO_EXTS
                    or child.suffix.lower() in Formats.AUDIO_EXTS
                ):
                    out.append(child)
        else:
            print(f"跳过（找不到）：{p}", file=sys.stderr)
    # 去重且保持顺序
    seen = set()
    uniq = []
    for f in out:
        key = str(f.resolve()).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def _quality_to_crf(q: int) -> int:
    """把 1-100 的质量映射到 CRF（越大质量越好 -> CRF 越小）。"""
    q = max(1, min(100, q))
    return int(round(51 - (q / 100.0) * 33))  # 100 -> 18, 1 -> 51


def cmd_version(args: argparse.Namespace) -> int:
    """打印版本信息：程序版本、发行者、内置组件版本。"""
    from . import __version__

    ff = FFmpeg.ffmpeg_path()
    caps = Formats.probe_ffmpeg(ff) if ff else Formats.FFmpegCaps()
    st = Images.plugin_status()
    print(f"{PROG} 版本 {__version__}")
    print(f"发行者     : xiaoke")
    print(f"ffmpeg     : {caps.version if ff else '未找到'}")
    print(f"HEIC / AVIF: {'支持' if st.get('heif') else '不支持'} / {'支持' if st.get('avif') else '不支持'}")
    print(f"可输出格式 : 图片 {len(Formats.available_image_formats())} 种，"
          f"视频音频 {len(Formats.available_video_targets(caps))} 种")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    from .Jobs import detect_kind

    caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
    print(f"{PROG} — 本机格式能力")
    print("=" * 66)
    ff = FFmpeg.ffmpeg_path()
    print(f"ffmpeg : {ff if ff else '未找到（视频转换不可用）'}")
    if ff:
        print(f"版本   : {caps.version}")
        print(f"硬件加速: {', '.join(sorted(caps.hwaccels)) or '无'}")
    print(f"ffprobe: {FFmpeg.ffprobe_path() or '未找到'}")
    st = Images.plugin_status()
    print(f"HEIC   : {'支持' if st['heif'] else '不支持'}")
    print(f"AVIF   : {'支持' if st['avif'] else '不支持'}")

    print("\n可输出的图片格式：")
    for f in Formats.available_image_formats():
        tags = []
        if f.supports_alpha:
            tags.append("透明")
        if f.supports_multi:
            tags.append("动图")
        tag = f"  [{'/'.join(tags)}]" if tags else ""
        print(f"  {f.ext:<7} {f.label}{tag}   {f.notes}")

    print("\n可输出的视频/音频格式：")
    targets = Formats.available_video_targets(caps)
    if not targets:
        print("  （需要 ffmpeg；请把 ffmpeg.exe 放到程序目录的 bin\\ 下）")
    for t in targets:
        print(f"  {t.ext:<7} {t.label}   {t.notes}")

    print(f"\n可读取的图片扩展名：{len(Formats.readable_image_exts())} 种")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    from .Jobs import ConvertSettings, JobRunner, Kind, State

    inputs = _collect_inputs(args.inputs)
    if not inputs:
        print("没有可转换的输入文件", file=sys.stderr)
        return 2

    settings = ConvertSettings()
    settings.out_dir = Path(args.outdir).resolve() if args.outdir else None
    settings.overwrite = bool(args.overwrite)
    settings.suffix = args.suffix

    # 图片参数
    settings.image.quality = args.quality
    settings.image.keep_metadata = bool(args.keep_metadata)
    if args.resize:
        mode, _, val = args.resize.partition("=")
        settings.image.resize_mode = mode or "percent"
        try:
            settings.image.resize_value = float(val) if val else float(args.resize)
            if not val:
                settings.image.resize_mode = "percent"
        except ValueError:
            settings.image.resize_mode = "none"
    if args.bg:
        settings.image.background = args.bg

    # 视频参数
    settings.video.target_key = args.target
    settings.video.crf_override = _quality_to_crf(args.quality) if args.crf is None else args.crf
    settings.video.quality = args.preset
    settings.video.scale = args.scale
    settings.video.fps = args.fps
    settings.video.copy_streams = bool(args.copy)
    settings.video.audio_mode = args.audio
    settings.video.audio_bitrate = args.audio_bitrate
    if args.trim:
        a, _, b = args.trim.partition("-")
        settings.video.trim_start = float(a or 0)
        settings.video.trim_end = float(b or 0)

    # 图片目标格式：如果用户给的是图片格式名，就设成图片目标
    img_formats = {f.key.upper(): f for f in Formats.available_image_formats()}
    video_keys = {t.key for t in Formats.VIDEO_TARGETS}
    tgt = args.target
    if tgt.upper() in img_formats:
        settings.image.target_key = img_formats[tgt.upper()].key
    elif tgt in video_keys:
        settings.video.target_key = tgt
    else:
        # 允许直接写扩展名
        by_ext = {f.ext.lstrip("."): f for f in Formats.available_image_formats()}
        by_ext.update({t.ext.lstrip("."): t for t in Formats.available_video_targets(
            Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps())})
        key = by_ext.get(tgt.lower().lstrip("."))
        if key is None:
            print(f"不认识的目标格式：{tgt}（可用 --list 查看）", file=sys.stderr)
            return 2
        if hasattr(key, "muxer"):
            settings.video.target_key = key.key
        else:
            settings.image.target_key = key.key

    runner = JobRunner(
        on_job_update=(None if (args.json or args.json_out) else _print_progress),
        on_finished=lambda jobs: None,
    )
    runner.add(inputs)
    if not runner.start(settings):
        print("已有任务在运行", file=sys.stderr)
        return 1
    assert runner._thread is not None
    runner._thread.join()

    jobs = runner.jobs
    ok = [j for j in jobs if j.state == State.DONE]
    bad = [j for j in jobs if j.state in (State.FAILED, State.CANCELLED)]
    print()
    print("=" * 66)
    for j in jobs:
        if j.state == State.DONE:
            print(f"✓ {j.name}  ->  {j.output.name}   {j.ratio_text}   {j.elapsed:.1f}s")
        elif j.state == State.FAILED:
            print(f"✗ {j.name}  失败：{j.error}")
        else:
            print(f"- {j.name}  {j.state.value}")
    print(f"完成 {len(ok)} 个，失败 {len(bad)} 个")

    report = [
        {
            "input": str(j.src),
            "output": str(j.output) if j.output else None,
            "state": j.state.value,
            "in_size": j.in_size,
            "out_size": j.out_size,
            "elapsed": round(j.elapsed, 3),
            "error": j.error or None,
        }
        for j in jobs
    ]
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 报告已写入：{out_path}")
    elif args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not bad else 1


def _print_progress(job) -> None:
    if job.state.value == "running":
        pct = int(job.progress * 100)
        bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
        sys.stdout.write(f"\r  [{bar}] {pct:3d}%  {job.name[:36]:<36} {job.speed:<8}")
        sys.stdout.flush()


def cmd_list(args: argparse.Namespace) -> int:
    caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
    print("图片格式 key：")
    print("  " + "  ".join(f.key for f in Formats.available_image_formats()))
    print("\n视频/音频格式 key：")
    print("  " + "  ".join(t.key for t in Formats.available_video_targets(caps)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="图片 / 视频 / 音频格式转换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command")

    p_info = sub.add_parser("info", help="查看本机支持的格式")
    p_info.set_defaults(func=cmd_info)

    p_ver = sub.add_parser("version", help="查看程序版本与发行信息")
    p_ver.set_defaults(func=cmd_version)

    p_list = sub.add_parser("list", help="列出目标格式的 key")
    p_list.set_defaults(func=cmd_list)

    p_conv = sub.add_parser("convert", help="转换文件（支持批量/通配符）")
    p_conv.add_argument("inputs", nargs="+", help="输入文件、目录或通配符")
    p_conv.add_argument("-t", "--target", required=True, help="目标格式（key 或扩展名，如 WEBP / png / mp4_h264 / webm_vp9）")
    p_conv.add_argument("-o", "--outdir", help="输出目录（默认与源文件同目录）")
    p_conv.add_argument("-q", "--quality", type=int, default=90, help="质量 1-100（图片质量/视频 CRF 换算），默认 90")
    p_conv.add_argument("--crf", type=int, help="直接指定视频 CRF（0-51，越小越好）")
    p_conv.add_argument("--preset", choices=["high", "balanced", "small", "tiny"], default="balanced",
                        help="视频质量档位，默认 balanced")
    p_conv.add_argument("--scale", default="keep", help="视频缩放：keep/2160/1440/1080/720/480/360")
    p_conv.add_argument("--fps", type=float, default=0, help="视频帧率（0 保持原样）")
    p_conv.add_argument("--resize", help="图片缩放：percent=50 / width=1920 / height=1080 / max=2000 / exact=800x600")
    p_conv.add_argument("--bg", default="#FFFFFF", help="透明图转不透明格式时的背景色")
    p_conv.add_argument("--keep-metadata", action="store_true", help="保留 EXIF 等元数据")
    p_conv.add_argument("--copy", action="store_true", help="仅换容器不重编码（极快，但要求编码兼容）")
    p_conv.add_argument("--audio", choices=["keep", "encode", "none"], default="encode", help="音频处理方式")
    p_conv.add_argument("--audio-bitrate", default="192k", help="音频码率，默认 192k")
    p_conv.add_argument("--trim", help="裁剪时间段，如 10-30 表示第 10 秒到第 30 秒")
    p_conv.add_argument("--suffix", default="_converted", help="输出文件名后缀")
    p_conv.add_argument("--overwrite", action="store_true", help="允许覆盖同名输出")
    p_conv.add_argument("--json", action="store_true", help="输出 JSON 结果报告")
    p_conv.add_argument("--json-out", help="把 JSON 结果报告写入指定文件（推荐给脚本调用）")
    p_conv.set_defaults(func=cmd_convert)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # 无参数：GUI 环境就开界面，否则打印帮助
    if not argv:
        try:
            from .Gui import run_gui

            return run_gui()
        except Exception:
            build_parser().print_help()
            return 0
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not getattr(ns, "func", None):
        parser.print_help()
        return 0
    return ns.func(ns)
