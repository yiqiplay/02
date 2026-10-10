"""用真实网络素材测试 MediaConv。

与 tests/ 里的自造样本不同，这里的输入全部是从公网下载的真实文件
（各类相机/手机/工具产出的图片、不同编码的视频与音频），
更能暴露真实世界的问题。

每个用例都会把输出文件用 ffprobe / Pillow 读回来校验，而不是只看"文件存在"。

用法（先下载素材，见 docs/TESTING.md）：

    # 1) 下载素材
    node tools/fetch-testfiles.mjs .cache/webtest
    node tools/fetch-missing-formats.mjs .cache/webtest

    # 2) 跑测试（--exe 传打包好的程序，或 tools/run-source-cli.py 跑源码）
    python tools/test-with-webfiles.py \\
        --exe dist/MediaConv/MediaConv.exe \\
        --indir .cache/webtest \\
        --outdir .cache/webtest-out
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

Formats.register_image_plugins()

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {PASS: "[OK]  ", FAIL: "[FAIL]", SKIP: "[SKIP]"}[status]
    print(f"{mark} {name}" + (f"   {detail}" if detail else ""))


def run_convert(exe: Path, src: Path, target: str, outdir: Path,
                extra: list[str] | None = None) -> tuple[bool, str, Path | None]:
    outdir.mkdir(parents=True, exist_ok=True)
    report = outdir / "_r.json"
    if report.exists():
        report.unlink()
    args = [str(exe), "convert", str(src), "-t", target, "-o", str(outdir),
            "--json-out", str(report)]
    if extra:
        args += extra
    p = subprocess.run(args, capture_output=True, timeout=900)
    log = (p.stdout + p.stderr).decode("utf-8", "replace")
    if not report.exists():
        return False, f"无报告 exit={p.returncode} {log[-200:]}", None
    try:
        entry = json.loads(report.read_text(encoding="utf-8"))[0]
    except Exception as e:
        return False, f"报告解析失败 {e}", None
    if entry.get("state") != "done" or not entry.get("output"):
        return False, (entry.get("error") or entry.get("state") or "?")[:200], None
    out = Path(entry["output"])
    if not out.exists() or out.stat().st_size == 0:
        return False, "输出为空", None
    return True, "", out


def verify_media(out: Path, *, vcodec: str | None = None, acodec: str | None = None,
                 has_video: bool | None = None) -> tuple[bool, str]:
    """用 ffprobe 读回输出并校验编码器。"""
    info = FFmpeg.probe(out)
    problems = []
    if has_video is True and not info.has_video and not out.suffix.lower() in (".gif", ".webp", ".apng"):
        problems.append("没有视频轨")
    if vcodec and info.vcodec and info.vcodec != vcodec:
        problems.append(f"编码 {info.vcodec}≠{vcodec}")
    if acodec and info.has_audio and info.acodec != acodec:
        problems.append(f"音频 {info.acodec}≠{acodec}")
    detail = f"{info.vcodec or info.acodec or info.format_name}"
    if info.width:
        detail += f" {info.width}x{info.height}"
    if info.duration:
        detail += f" {info.duration:.1f}s"
    detail += f" {out.stat().st_size/1024:.0f}KB"
    return (not problems), (("; ".join(problems) + " | ") if problems else "") + detail


def verify_image(out: Path) -> tuple[bool, str]:
    from PIL import Image
    try:
        with Image.open(out) as im:
            im.load()
            n = getattr(im, "n_frames", 1)
            d = f"{im.format} {im.width}x{im.height}"
            if n > 1:
                d += f" {n}帧"
            return True, d + f" {out.stat().st_size/1024:.0f}KB"
    except Exception as e:
        return False, f"读回失败 {e}"


# ----------------------------------------------------------------- 用例定义

# 图片：输入 -> [(目标格式, 额外参数, 校验是否用 Pillow)]
IMAGE_CASES = [
    ("jpg_from_web.jpg", [("WEBP", ["-q", "85"], True), ("PNG", [], True), ("AVIF", [], True), ("HEIC", [], True)]),
    ("png_from_web.png", [("JPEG", ["-q", "90"], True), ("WEBP", ["-q", "80"], True)]),
    ("webp_from_web.webp", [("JPEG", [], True), ("PNG", [], True)]),
    ("gif_from_web.gif", [("PNG", [], True), ("WEBP", [], True), ("JPEG", [], True)]),
    ("bmp_from_web.bmp", [("PNG", [], True), ("JPEG", [], True), ("TIFF", [], True)]),
    ("tiff_from_web.tiff", [("JPEG", [], True), ("PNG", [], True)]),
    ("ico_from_web.ico", [("PNG", [], True), ("JPEG", [], True)]),
    ("heic_from_web.heic", [("JPEG", [], True), ("PNG", [], True)]),
    ("avif_from_web.avif", [("JPEG", [], True), ("PNG", [], True)]),
]

# 视频：输入 -> [(目标, 额外参数, 期望视频编码, 期望音频编码)]
VIDEO_CASES = [
    ("mp4_from_web.mp4", [("webm_vp9", [], "vp9", "opus"), ("mp4_h265", [], "hevc", "aac"),
                          ("mkv_h264", [], "h264", "aac")]),
    ("webm_from_web.webm", [("mp4_h264", [], "h264", "aac"), ("avi_mpeg4", [], "mpeg4", None)]),
    ("avi_from_web.avi", [("mp4_h264", [], "h264", "aac"), ("mkv_h264", [], "h264", "aac")]),
    ("mov_from_web.mov", [("mp4_h264", [], "h264", "aac")]),
    ("flv_from_web.flv", [("mp4_h264", [], "h264", None)]),
    ("wmv_from_web.wmv", [("mp4_h264", [], "h264", None)]),
    ("mpg_from_web.mpg", [("mp4_h264", [], "h264", None)]),
    ("ts_from_web.ts", [("mp4_h264", [], "h264", None)]),
    ("3gp_from_web.3gp", [("mp4_h264", [], "h264", None)]),
    ("mp4_from_web.mp4", [("gif_anim", ["--fps", "10", "--scale", "240"], None, None)]),
]

# 音频：输入 -> [(目标, 期望编码)]
AUDIO_CASES = [
    ("mp3_from_web.mp3", [("m4a", "aac"), ("flac", "flac"), ("wav", "pcm_s16le"), ("ogg_audio", "vorbis")]),
    ("wav_from_web.wav", [("mp3", "mp3"), ("opus", "opus"), ("aac", "aac")]),
    ("flac_from_web.flac", [("mp3", "mp3"), ("m4a", "aac")]),
    ("ogg_from_web.ogg", [("mp3", "mp3"), ("wav", "pcm_s16le")]),
    ("m4a_from_web.m4a", [("mp3", "mp3"), ("flac", "flac")]),
    ("aac_from_web.aac", [("mp3", "mp3"), ("wav", "pcm_s16le")]),
]

# 预期会"优雅失败"的用例：输入缺少目标所需的流。
# 注意：公网下载的这些测试短片（mp4/mov/avi/webm/wmv/flv/mpg/ts/3gp）
# 全部只有视频轨、没有音轨，所以"从视频提取音频"在这里属于负向用例。
# 这里要验证的不是转换成功，而是给出人类能看懂的提示，
# 而不是把 ffmpeg 的 "Invalid argument" 直接甩给用户。
NEGATIVE_CASES = [
    ("mp4_from_web.mp4", "mp3", "没有音轨", "无音轨视频 → 提取 MP3"),
    ("mov_from_web.mov", "m4a", "没有音轨", "无音轨视频 → 提取 M4A"),
    ("avi_from_web.avi", "flac", "没有音轨", "无音轨视频 → 提取 FLAC"),
    ("mp3_from_web.mp3", "mp4_h264", "没有视频轨", "纯音频 → MP4"),
    ("ogg_from_web.ogg", "webm_vp9", "没有视频轨", "纯音频 → WebM"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    exe = Path(a.exe)
    indir = Path(a.indir)
    outdir = Path(a.outdir)
    if not exe.exists():
        print(f"找不到程序：{exe}")
        return 2
    if not indir.is_dir():
        print(f"找不到素材目录：{indir}")
        return 2

    print("=" * 74)
    print("真实网络素材转换测试")
    print(f"  被测程序：{exe}")
    print(f"  素材目录：{indir}")
    print(f"  输出目录：{outdir}")
    print("=" * 74)

    n = 0

    print("\n---------------- 图片 ----------------")
    for srcname, targets in IMAGE_CASES:
        src = indir / srcname
        if not src.exists():
            record(f"图片 {srcname}", SKIP, "素材缺失")
            continue
        for target, extra, use_pil in targets:
            n += 1
            sub = outdir / "img" / srcname.split("_")[0] / target.lower()
            ok, err, out = run_convert(exe, src, target, sub, extra)
            label = f"图片 {srcname} → {target}"
            if not ok:
                record(label, FAIL, err)
                continue
            good, detail = verify_image(out) if use_pil else verify_media(out)
            record(label, PASS if good else FAIL, detail)

    print("\n---------------- 视频 ----------------")
    for srcname, targets in VIDEO_CASES:
        src = indir / srcname
        if not src.exists():
            record(f"视频 {srcname}", SKIP, "素材缺失")
            continue
        for target, extra, vc, ac in targets:
            n += 1
            sub = outdir / "vid" / srcname.split("_")[0] / target
            ok, err, out = run_convert(exe, src, target, sub, extra)
            label = f"视频 {srcname} → {target}"
            if not ok:
                record(label, FAIL, err)
                continue
            good, detail = verify_media(out, vcodec=vc, acodec=ac, has_video=True)
            record(label, PASS if good else FAIL, detail)

    print("\n---------------- 音频 ----------------")
    for srcname, targets in AUDIO_CASES:
        src = indir / srcname
        if not src.exists():
            record(f"音频 {srcname}", SKIP, "素材缺失")
            continue
        for target, ac in targets:
            n += 1
            sub = outdir / "aud" / srcname.split("_")[0] / target
            ok, err, out = run_convert(exe, src, target, sub)
            label = f"音频 {srcname} → {target}"
            if not ok:
                record(label, FAIL, err)
                continue
            good, detail = verify_media(out, acodec=ac, has_video=False)
            record(label, PASS if good else FAIL, detail)

    print("\n---------------- 边界情况（应优雅报错） ----------------")
    for srcname, target, expect_kw, label in NEGATIVE_CASES:
        src = indir / srcname
        if not src.exists():
            record(label, SKIP, "素材缺失")
            continue
        sub = outdir / "neg" / srcname.split("_")[0] / target
        ok, err, out = run_convert(exe, src, target, sub)
        if ok:
            record(label, FAIL, "本该报错却转换成功了")
            continue
        # 必须给出人类能看懂的中文说明，而不是 ffmpeg 的原始报错
        readable = expect_kw in err
        raw_ffmpeg = "Invalid argument" in err or "Error opening output" in err
        if readable and not raw_ffmpeg:
            record(label, PASS, err.splitlines()[0][:70])
        else:
            record(label, FAIL, f"提示不清晰：{err.splitlines()[0][:80]}")

    npass = sum(1 for _, s, _ in results if s == PASS)
    nfail = sum(1 for _, s, _ in results if s == FAIL)
    nskip = sum(1 for _, s, _ in results if s == SKIP)
    print("\n" + "=" * 74)
    print(f"总计 {len(results)} 项：通过 {npass}，失败 {nfail}，跳过 {nskip}")
    if nfail:
        print("\n失败明细：")
        for name, s, d in results:
            if s == FAIL:
                print(f"  - {name}: {d}")
    print("=" * 74)

    rep = PROJ / "tests" / "web-test-report.md"
    with open(rep, "w", encoding="utf-8") as f:
        f.write("# 真实网络素材转换测试报告\n\n")
        f.write(f"- 被测程序：`{exe}`\n")
        f.write(f"- 素材来源：公网下载的真实图片/视频/音频（{len(list(indir.glob('*')))} 个文件）\n")
        f.write(f"- 结果：通过 {npass} / 失败 {nfail} / 跳过 {nskip}（共 {len(results)} 项）\n\n")
        f.write("| 测试项 | 结果 | 说明 |\n|---|---|---|\n")
        for name, s, d in results:
            icon = {PASS: "✅", FAIL: "❌", SKIP: "⏭️"}[s]
            f.write(f"| {name} | {icon} {s} | {d.replace('|', '\\|')} |\n")
    print(f"\n报告已写入 {rep}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
