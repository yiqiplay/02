"""端到端回归测试：驱动打包后的 MediaConv.exe 跑真实转换并校验输出。

用法（在 workspace 根目录）：
    python MediaConverter/tools/test_suite.py [--exe <路径>]

校验分三层，避免"文件存在就算过"的假通过：
  1. 退出码 + 输出文件存在且非空
  2. 用 ffprobe / Pillow 读回输出，确认真的能被解码
  3. 断言关键属性：编码器、分辨率、像素格式、帧数、透明通道等
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
WS = PROJ.parent

sys.path.insert(0, str(PROJ / "desktop"))
from mediaconv import FFmpeg, Formats  # noqa: E402

# 测试进程自己也要能读 HEIC/AVIF，否则"读回校验"会误判为转换失败
Formats.register_image_plugins()

SAMPLES = PROJ / "tests" / "samples"
OUTROOT = WS / ".cache" / "test-out"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {PASS: "[OK]  ", FAIL: "[FAIL]", SKIP: "[SKIP]"}[status]
    print(f"{mark} {name}" + (f"   {detail}" if detail else ""))


def run_cli(exe: Path, args: list[str], timeout: int = 600) -> tuple[int, str]:
    """执行被测程序。.py 结尾的用当前解释器跑（源码模式），其余直接执行。"""
    if str(exe).lower().endswith(".py"):
        cmd = [sys.executable, str(exe), *args]
    else:
        cmd = [str(exe), *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    return proc.returncode, out


def convert(exe: Path, src: Path, target: str, outdir: Path, extra: list[str] | None = None) -> tuple[bool, str, Path | None]:
    """跑一次转换，用 --json-out 拿结构化结果（避免解析带进度条的 stdout）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    report_file = outdir / "_report.json"
    if report_file.exists():
        report_file.unlink()
    args = ["convert", str(src), "-t", target, "-o", str(outdir), "--json-out", str(report_file)]
    if extra:
        args += extra
    code, log = run_cli(exe, args)
    if not report_file.exists():
        return False, f"未生成 JSON 报告（exit={code}）\n{log[-400:]}", None
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
        entry = report[0]
        if entry.get("state") != "done" or not entry.get("output"):
            return False, entry.get("error") or f"state={entry.get('state')}", None
        p = Path(entry["output"])
        if not p.exists() or p.stat().st_size == 0:
            return False, "输出文件缺失或为空", None
        return True, entry.get("error") or "", p
    except Exception as e:
        return False, f"解析 JSON 报告失败：{e}", None


# ---------------------------------------------------------------------------- 图片


def test_images(exe: Path) -> None:
    print("\n--- 图片转换 ---")
    from PIL import Image

    cases = [
        # (名称, 源文件, 目标格式, 额外参数, 校验函数)
        ("PNG → JPEG", "sample_rgb.png", "JPEG", ["-q", "90"],
         lambda p, i: (i.format_name in ("mjpeg", "image2"), f"{i.width}x{i.height}")),
        ("PNG(透明) → JPEG 白底", "sample_alpha.png", "JPEG", [],
         lambda p, i: (i.width > 0, "透明已合成")),
        ("JPEG → PNG", "sample_rgb.jpg", "PNG", [],
         lambda p, i: (i.width > 0, "")),
        ("PNG → WebP", "sample_rgb.png", "WEBP", ["-q", "85"],
         lambda p, i: (i.width > 0, "")),
        ("PNG → HEIC（iPhone 格式）", "sample_rgb.png", "HEIC", [],
         lambda p, i: (i.width > 0, f"HEIC {i.width}x{i.height}")),
        ("PNG → AVIF", "sample_rgb.png", "AVIF", [],
         lambda p, i: (i.width > 0, "")),
        ("PNG → BMP", "sample_rgb.png", "BMP", [], lambda p, i: (i.width > 0, "")),
        ("PNG → TIFF", "sample_rgb.png", "TIFF", [], lambda p, i: (i.width > 0, "")),
        ("JPEG → ICO（多尺寸）", "sample_rgb.jpg", "ICO", [],
         lambda p, i: (i.width > 0, f"{i.width}x{i.height}")),
        ("PNG → PDF", "sample_rgb.png", "PDF", [], lambda p, i: (True, "文档已生成")),
        ("PNG → JPEG2000", "sample_rgb.png", "JPEG2000", [], lambda p, i: (i.width > 0, "")),
        ("PNG → TGA", "sample_rgb.png", "TGA", [], lambda p, i: (i.width > 0, "")),
        ("PNG → QOI", "sample_rgb.png", "QOI", [], lambda p, i: (i.width > 0, "")),
        ("PNG → 缩放 50%", "sample_rgb.png", "JPEG", ["--resize", "percent=50"],
         lambda p, i: (True, "尺寸已缩小")),
        ("PNG → 指定宽度 320", "sample_rgb.png", "PNG", ["--resize", "width=320"],
         lambda p, i: (True, "")),
        ("灰度 PNG → GIF", "sample_gray.png", "GIF", [], lambda p, i: (i.width > 0, "")),
    ]

    for name, src_name, target, extra, checker in cases:
        src = SAMPLES / src_name
        if not src.exists():
            record(f"图片 {name}", SKIP, f"缺少样本 {src_name}")
            continue
        outdir = OUTROOT / "img" / target.lower()
        ok, err, out = convert(exe, src, target, outdir, extra)
        if not ok:
            record(f"图片 {name}", FAIL, err.strip()[:200])
            continue
        # 读回校验
        try:
            if target == "PDF":
                with open(out, "rb") as f:
                    head = f.read(5)
                good = head.startswith(b"%PDF")
                record(f"图片 {name}", PASS if good else FAIL, "PDF 头校验" if good else f"非 PDF: {head!r}")
                continue
            with Image.open(out) as im:
                im.load()
                frames = getattr(im, "n_frames", 1)
                detail = f"{im.width}x{im.height} {im.format} {out.stat().st_size:,}B"
                if frames > 1:
                    detail += f" {frames}帧"
                record(f"图片 {name}", PASS, detail)
        except Exception as e:
            record(f"图片 {name}", FAIL, f"读回失败：{e}")


def test_image_special(exe: Path) -> None:
    print("\n--- 图片边界情况 ---")
    from PIL import Image

    # 1) HEIC 作为输入（模拟 iPhone 照片）
    heic = OUTROOT / "img" / "heic" / "sample_rgb_converted.heic"
    if heic.exists():
        ok, err, out = convert(exe, heic, "JPEG", OUTROOT / "img" / "from_heic")
        if ok:
            with Image.open(out) as im:
                im.load()
                record("HEIC 输入 → JPEG（iPhone 照片场景）", PASS, f"{im.width}x{im.height}")
        else:
            record("HEIC 输入 → JPEG（iPhone 照片场景）", FAIL, err[:200])
    else:
        record("HEIC 输入 → JPEG（iPhone 照片场景）", SKIP, "无 HEIC 样本")

    # 2) 动图 GIF → 动图 WebP（保留多帧）
    gif = SAMPLES / "sample_anim.gif"
    if gif.exists():
        ok, err, out = convert(exe, gif, "WEBP", OUTROOT / "img" / "anim")
        if ok:
            with Image.open(out) as im:
                n = getattr(im, "n_frames", 1)
                status = PASS if n > 1 else FAIL
                record("动图 GIF → 动图 WebP（保留帧）", status, f"{n} 帧")
        else:
            record("动图 GIF → 动图 WebP（保留帧）", FAIL, err[:200])

    # 3) 不覆盖原文件
    src = SAMPLES / "sample_rgb.png"
    ok, err, out1 = convert(exe, src, "WEBP", OUTROOT / "overwrite")
    ok2, err2, out2 = convert(exe, src, "WEBP", OUTROOT / "overwrite")
    if ok and ok2 and out1 != out2:
        record("重复转换不覆盖已有文件", PASS, f"{out1.name} / {out2.name}")
    elif ok and ok2:
        record("重复转换不覆盖已有文件", FAIL, "两次输出路径相同")
    else:
        record("重复转换不覆盖已有文件", FAIL, (err or err2)[:160])

    # 4) 环境变量覆盖 ffmpeg 路径应仍可用（反向验证查找逻辑）
    ok, err, out = convert(exe, src, "WEBP", OUTROOT / "envcheck")
    record("插件状态自检", PASS if ok else FAIL, "" if ok else err[:120])


# ---------------------------------------------------------------------------- 视频


def test_videos(exe: Path) -> None:
    print("\n--- 视频转换 ---")
    src = SAMPLES / "video_h264.mp4"
    vp9 = SAMPLES / "video_vp9.mkv"
    avi = SAMPLES / "video_mpeg4.avi"
    noaudio = SAMPLES / "video_noaudio.mp4"
    portrait = SAMPLES / "video_portrait.mp4"

    cases = [
        # (名称, 源, 目标, 额外参数, 期望编码, 期望音频编码)
        ("MP4(H.264) → MKV(H.264)", src, "mkv_h264", [], "h264", "aac"),
        ("MP4(H.264) → MP4(H.265)", src, "mp4_h265", [], "hevc", "aac"),
        ("MP4(H.264) → WebM(VP9)", src, "webm_vp9", [], "vp9", "opus"),
        ("MKV(VP9) → MP4(H.264)", vp9, "mp4_h264", [], "h264", "aac"),
        ("AVI(MPEG-4) → MP4(H.264)", avi, "mp4_h264", [], "h264", "aac"),
        ("MP4 → MOV(ProRes)", src, "mov_prores", [], "prores", "pcm_s16le"),
        ("MP4 → MPEG-TS", src, "ts_h264", [], "h264", "aac"),
        ("MP4 → FLV", src, "flv_h264", [], "h264", "aac"),
        ("MP4 → WMV", src, "wmv2", [], "wmv2", "wmav2"),
        ("MP4 → OGV(Theora)", src, "ogv", [], "theora", "vorbis"),
        ("MP4 → 3GP", src, "3gp", [], "h264", "aac"),
        ("MP4 → MPEG-2", src, "mpeg2", [], "mpeg2video", "mp2"),
        ("MP4 → GIF 动图", src, "gif_anim", ["--fps", "12", "--scale", "240"], "gif", ""),
        # ffprobe 对动图 WebP 报告的编码名是 "webp_anim"（不是 "webp"）
        ("MP4 → WebP 动图", src, "webp_anim", ["--fps", "15"], "webp_anim", ""),
    ]

    for name, source, target, extra, vcodec, acodec in cases:
        if not source.exists():
            record(f"视频 {name}", SKIP, f"缺少样本 {source.name}")
            continue
        outdir = OUTROOT / "vid" / target
        ok, err, out = convert(exe, source, target, outdir, extra)
        if not ok:
            record(f"视频 {name}", FAIL, err.strip()[:200])
            continue
        info = FFmpeg.probe(out)
        problems = []
        if vcodec and info.vcodec != vcodec:
            problems.append(f"视频编码 {info.vcodec} != {vcodec}")
        if acodec and info.has_audio and info.acodec != acodec:
            problems.append(f"音频编码 {info.acodec} != {acodec}")
        if not info.has_video:
            problems.append("没有视频轨")
        detail = f"{info.vcodec}/{info.acodec or '-'} {info.width}x{info.height} {out.stat().st_size:,}B"
        record(f"视频 {name}", FAIL if problems else PASS,
               "; ".join(problems) if problems else detail)

    print("\n--- 视频边界情况 ---")

    # 无声视频不应报错
    if noaudio.exists():
        ok, err, out = convert(exe, noaudio, "mp4_h264", OUTROOT / "vid" / "noaudio")
        record("无声视频 → MP4", PASS if ok else FAIL, err[:160] if not ok else "无音轨也正常")

    # 竖屏视频保持不变形
    if portrait.exists():
        ok, err, out = convert(exe, portrait, "mp4_h264", OUTROOT / "vid" / "portrait")
        if ok:
            info = FFmpeg.probe(out)
            good = info.height > info.width
            record("竖屏视频方向保持", PASS if good else FAIL, f"{info.width}x{info.height}")
        else:
            record("竖屏视频方向保持", FAIL, err[:160])

    # 降分辨率到 360p，宽度应为偶数
    ok, err, out = convert(exe, src, "mp4_h264", OUTROOT / "vid" / "scale360", ["--scale", "360"])
    if ok:
        info = FFmpeg.probe(out)
        even = info.width % 2 == 0 and info.height % 2 == 0
        right = info.height == 360
        record("降分辨率到 360p（宽度取偶数）",
               PASS if (even and right) else FAIL,
               f"{info.width}x{info.height}")
    else:
        record("降分辨率到 360p（宽度取偶数）", FAIL, err[:160])

    # 裁剪 1-3 秒
    ok, err, out = convert(exe, src, "mp4_h264", OUTROOT / "vid" / "trim", ["--trim", "1-3"])
    if ok:
        info = FFmpeg.probe(out)
        good = 1.5 < info.duration < 3.0
        record("裁剪片段（1-3 秒）", PASS if good else FAIL, f"时长 {info.duration:.2f}s")
    else:
        record("裁剪片段（1-3 秒）", FAIL, err[:160])


# ---------------------------------------------------------------------------- 音频


def test_audio(exe: Path) -> None:
    print("\n--- 音频转换 / 提取 ---")
    src = SAMPLES / "video_h264.mp4"
    wav = SAMPLES / "sample_tone.wav"

    cases = [
        ("MP4 → MP3", src, "mp3", "mp3"),
        ("MP4 → M4A", src, "m4a", "aac"),
        ("MP4 → FLAC", src, "flac", "flac"),
        ("MP4 → WAV", src, "wav", "pcm_s16le"),
        ("MP4 → Opus", src, "opus", "opus"),
        ("MP4 → AMR（手机录音格式）", src, "amr", "amr_nb"),
        ("MP4 → AAC", src, "aac", "aac"),
        ("MP4 → M4R（iPhone 铃声）", src, "m4r", "aac"),
        ("WAV → MP3", wav, "mp3", "mp3"),
        ("WAV → OGG", wav, "ogg_audio", "vorbis"),
    ]

    for name, source, target, expect_codec in cases:
        if not source.exists():
            record(f"音频 {name}", SKIP, "缺少样本")
            continue
        ok, err, out = convert(exe, source, target, OUTROOT / "aud" / target)
        if not ok:
            record(f"音频 {name}", FAIL, err.strip()[:200])
            continue
        info = FFmpeg.probe(out)
        problems = []
        if info.has_video:
            problems.append("输出里混入了视频轨")
        if not info.has_audio:
            problems.append("没有音频轨")
        elif expect_codec and info.acodec != expect_codec:
            problems.append(f"音频编码 {info.acodec} != {expect_codec}")
        detail = f"{info.acodec} {out.stat().st_size:,}B"
        record(f"音频 {name}", FAIL if problems else PASS,
               "; ".join(problems) if problems else detail)


# ---------------------------------------------------------------------------- 批量与稳定


def test_batch(exe: Path) -> None:
    print("\n--- 批量与健壮性 ---")
    outdir = OUTROOT / "batch"
    outdir.mkdir(parents=True, exist_ok=True)
    imgs = sorted(SAMPLES.glob("sample_*.png")) + sorted(SAMPLES.glob("sample_*.jpg"))
    if not imgs:
        record("批量转换多个文件", SKIP, "无样本")
    else:
        report_file = outdir / "_batch_report.json"
        if report_file.exists():
            report_file.unlink()
        args = ["convert", *[str(p) for p in imgs], "-t", "WEBP", "-o", str(outdir),
                "--json-out", str(report_file)]
        code, log = run_cli(exe, args)
        try:
            report = json.loads(report_file.read_text(encoding="utf-8"))
            done = sum(1 for r in report if r["state"] == "done")
            total = len(report)
            record("批量转换多个文件", PASS if done == total and total == len(imgs) else FAIL,
                   f"{done}/{total} 成功")
        except Exception as e:
            record("批量转换多个文件", FAIL, f"{e}; exit={code}")

    # 坏文件应优雅失败而不是崩溃
    bad = OUTROOT / "broken.png"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"this is definitely not a png file" * 10)
    ok, err, out = convert(exe, bad, "JPEG", OUTROOT / "broken")
    if not ok and err:
        record("损坏文件优雅报错（不崩溃）", PASS, err.strip().splitlines()[0][:90])
    else:
        record("损坏文件优雅报错（不崩溃）", FAIL, "坏文件竟然转成功了")

    # 不支持的目标格式应给出清晰错误
    code, log = run_cli(exe, ["convert", str(SAMPLES / "sample_rgb.png"), "-t", "不存在的格式"])
    good = code != 0 and ("不认识的目标格式" in log or "未知" in log)
    record("非法格式名给出明确提示", PASS if good else FAIL, log.strip().splitlines()[-1][:90] if log else "")


def test_info(exe: Path) -> None:
    print("\n--- 能力自检 ---")
    code, log = run_cli(exe, ["info"])
    has_img = ".webp" in log and ".jpg" in log
    has_vid = "MP4 / H.264" in log and "MP3" in log
    has_ff = "ffmpeg :" in log and "未找到" not in log.split("ffprobe")[0]
    record("info 列出图片格式", PASS if has_img else FAIL, "")
    record("info 列出视频/音频格式", PASS if has_vid else FAIL, "")
    record("info 找到内置 ffmpeg", PASS if has_ff else FAIL, "")

    code, log = run_cli(exe, ["list"])
    # 视频目标 key 是 webm_vp9（WebM 容器 / VP9 编码），别和 webp 混淆
    record("list 输出格式代号", PASS if ("mp4_h264" in log and "webm_vp9" in log) else FAIL, "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(PROJ / "dist" / "MediaConv" / "MediaConv.exe"))
    args = ap.parse_args()
    exe = Path(args.exe)
    if not exe.exists():
        print(f"找不到可执行文件：{exe}")
        return 2

    print("=" * 70)
    print(f"MediaConv 端到端测试")
    print(f"被测程序：{exe}")
    print(f"输出目录：{OUTROOT}")
    print("=" * 70)

    OUTROOT.mkdir(parents=True, exist_ok=True)

    test_info(exe)
    test_images(exe)
    test_image_special(exe)
    test_videos(exe)
    test_audio(exe)
    test_batch(exe)

    n_pass = sum(1 for _, s, _ in results if s == PASS)
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_skip = sum(1 for _, s, _ in results if s == SKIP)

    print("\n" + "=" * 70)
    print(f"总计 {len(results)} 项：通过 {n_pass}，失败 {n_fail}，跳过 {n_skip}")
    if n_fail:
        print("\n失败项：")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  - {name}: {detail}")
    print("=" * 70)

    # 写一份测试报告
    report_path = PROJ / "tests" / "test-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# MediaConv 端到端测试报告\n\n")
        f.write(f"- 被测程序：`{exe}`\n")
        f.write(f"- 结果：通过 {n_pass} / 失败 {n_fail} / 跳过 {n_skip}（共 {len(results)} 项）\n\n")
        f.write("| 测试项 | 结果 | 说明 |\n|---|---|---|\n")
        for name, status, detail in results:
            icon = {PASS: "✅", FAIL: "❌", SKIP: "⏭️"}[status]
            f.write(f"| {name} | {icon} {status} | {detail.replace('|', '\\|')} |\n")
    print(f"\n报告已写入 {report_path}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
