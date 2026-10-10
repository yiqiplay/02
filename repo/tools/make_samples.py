"""生成一套覆盖常见格式的测试图片/音频素材，供转换测试使用。"""

from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "desktop"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# HEIC/AVIF 需要插件注册后才能被 Pillow 识别为可写格式
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pass


def _font(size: int):
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_rgb(path: Path, size=(640, 400), label="RGB"):
    img = Image.new("RGB", size, (32, 64, 128))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(255, 200, 0), width=4)
    d.ellipse([60, 60, 260, 260], fill=(220, 60, 60))
    d.text((20, size[1] - 44), f"{label} {size[0]}x{size[1]}", fill=(255, 255, 255), font=_font(22))
    img.save(path)
    return path


def make_alpha(path: Path, size=(400, 400)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([20, 20, size[0] - 20, size[1] - 20], fill=(0, 180, 120, 200))
    d.text((40, size[1] // 2), "ALPHA", fill=(255, 255, 255, 255), font=_font(40))
    img.save(path)
    return path


def make_gray(path: Path, size=(300, 200)):
    img = Image.new("L", size, 128)
    ImageDraw.Draw(img).text((10, 10), "GRAYSCALE", fill=255, font=_font(24))
    img.save(path)
    return path


def make_animated_gif(path: Path, n=12, size=(240, 160)):
    frames = []
    for i in range(n):
        img = Image.new("P", size)
        img.putpalette([0, 0, 0, 255, 80, 80, 80, 255, 80, 80, 80, 255] + [0] * (768 - 12))
        d = ImageDraw.Draw(img)
        x = int(10 + (size[0] - 60) * i / max(1, n - 1))
        d.rectangle([x, 60, x + 40, 110], fill=1 + (i % 3))
        d.text((10, 10), f"frame {i+1}/{n}", fill=3, font=_font(16))
        frames.append(img)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80, loop=0)
    return path


def make_wav(path: Path, seconds=2.0, rate=44100):
    import math
    import struct

    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        total = int(rate * seconds)
        for i in range(total):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / rate))
            frames += struct.pack("<hh", v, v // 2)
        w.writeframes(bytes(frames))
    return path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "samples"
    out.mkdir(parents=True, exist_ok=True)
    made = []

    made.append(make_rgb(out / "sample_rgb.jpg", label="JPEG"))
    made.append(make_rgb(out / "sample_rgb.png", (800, 600), "PNG"))
    made.append(make_alpha(out / "sample_alpha.png"))
    made.append(make_gray(out / "sample_gray.png"))
    made.append(make_animated_gif(out / "sample_anim.gif"))
    made.append(make_rgb(out / "sample_photo.png", (1280, 720), "PHOTO"))
    made.append(make_wav(out / "sample_tone.wav"))

    # 用 Pillow 能写的格式尽量多造几个
    base = out / "sample_rgb.png"
    img = Image.open(base)
    for ext, fmt in ((".webp", "WEBP"), (".bmp", "BMP"), (".tiff", "TIFF"), (".tga", "TGA"),
                     (".ppm", "PPM"), (".pcx", "PCX"), (".ico", "ICO"), (".jp2", "JPEG2000")):
        try:
            img.save(out / f"sample{ext}", format=fmt)
            made.append(out / f"sample{ext}")
        except Exception as e:
            print(f"  跳过 {ext}: {e}")
    try:
        img.save(out / "sample.avif", format="AVIF", quality=80)
        made.append(out / "sample.avif")
    except Exception as e:
        print(f"  跳过 avif: {e}")
    try:
        img.save(out / "sample.heic", format="HEIF", quality=80)
        made.append(out / "sample.heic")
    except Exception as e:
        print(f"  跳过 heic: {e}")

    for p in made:
        print(f"  {p.name:<24} {p.stat().st_size:>9,} bytes")
    print(f"共生成 {len(made)} 个测试文件 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
