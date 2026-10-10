"""用 ffmpeg 生成一段真实测试视频（含音轨），供转换测试使用。

生成多种容器/编码组合，覆盖"市面上常见格式"的输入侧。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "desktop"))

from mediaconv import FFmpeg  # noqa: E402


def _run(args: list[str]) -> tuple[int, str]:
    exe = FFmpeg.ffmpeg_path()
    if exe is None:
        print("找不到 ffmpeg", file=sys.stderr)
        return 1, ""
    proc = subprocess.run([str(exe), "-hide_banner", "-y", "-nostdin", *args],
                          capture_output=True)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "samples"
    out.mkdir(parents=True, exist_ok=True)

    # 测试图案：带移动元素 + 时间码，方便肉眼确认转码是否正确
    src_filter = (
        "testsrc2=size=640x360:rate=25:duration=4,"
        "drawtext=text='MediaConv %{pts\\:hms}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
    )

    jobs: list[tuple[str, list[str]]] = [
        # 主测试源：MP4 / H.264 + AAC
        ("video_h264.mp4", [
            "-f", "lavfi", "-i", src_filter,
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
        ]),
        # 另一种常见输入：MKV / VP9 + Opus
        ("video_vp9.mkv", [
            "-f", "lavfi", "-i", src_filter,
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=4",
            "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", "0", "-cpu-used", "4", "-row-mt", "1",
            "-c:a", "libopus", "-b:a", "96k", "-shortest",
        ]),
        # 老格式输入：AVI / MPEG-4
        ("video_mpeg4.avi", [
            "-f", "lavfi", "-i", src_filter,
            "-f", "lavfi", "-i", "sine=frequency=550:sample_rate=44100:duration=4",
            "-c:v", "mpeg4", "-b:v", "1200k", "-c:a", "libmp3lame", "-b:a", "128k", "-shortest",
        ]),
        # 无声视频，测试无音轨输入
        ("video_noaudio.mp4", [
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15:duration=2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", "-an",
        ]),
        # 竖屏短视频（手机拍摄的典型形态）
        ("video_portrait.mp4", [
            "-f", "lavfi", "-i",
            "testsrc2=size=360x640:rate=30:duration=3,"
            "drawtext=text='PORTRAIT':x=40:y=280:fontsize=36:fontcolor=yellow",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-an",
        ]),
    ]

    ok = 0
    for name, args in jobs:
        dst = out / name
        if dst.exists():
            dst.unlink()
        code, log = _run([*args, str(dst)])
        if code == 0 and dst.exists() and dst.stat().st_size > 0:
            print(f"  {name:<22} {dst.stat().st_size:>9,} bytes")
            info = FFmpeg.probe(dst)
            print(f"      {info.describe()}")
            ok += 1
        else:
            print(f"  {name:<22} 失败")
            print("      " + "\n      ".join(log.splitlines()[-5:]))

    # 音频样本：m4a
    m4a = out / "audio_aac.m4a"
    code, log = _run(["-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100:duration=3",
                      "-c:a", "aac", "-b:a", "128k", str(m4a)])
    if code == 0 and m4a.exists():
        print(f"  {'audio_aac.m4a':<22} {m4a.stat().st_size:>9,} bytes")
        ok += 1
    else:
        print("  audio_aac.m4a 失败")

    print(f"生成 {ok}/{len(jobs) + 1} 个测试视频 -> {out}")
    return 0 if ok == len(jobs) + 1 else 1


if __name__ == "__main__":
    sys.exit(main())
