"""生成程序图标（.ico + .png），不依赖外部素材。

风格：蓝色圆角方块 + 白色"转"字 + 右下角一个小的格式箭头，
确保在 16x16 到 256x256 都还能辨认。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "assets"

BG_TOP = (28, 122, 214)
BG_BOTTOM = (12, 78, 168)
ACCENT = (255, 196, 0)


def _font(size: int):
    for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _vertical_gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def render(size: int) -> Image.Image:
    ss = 4  # 超采样，边缘更干净
    s = size * ss
    base = _vertical_gradient(s).convert("RGBA")

    # 圆角遮罩
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)

    # 右下角斜切一层浅色，增加层次
    overlay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(s, int(s * 0.55)), (s, s), (int(s * 0.45), s)], fill=(255, 255, 255, 28))

    img = Image.alpha_composite(base, overlay)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    # 主字
    f = _font(int(s * 0.56))
    text = "转"
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((s - tw) / 2 - bbox[0], (s - th) / 2 - bbox[1] - s * 0.02), text, font=f, fill=(255, 255, 255, 255))

    # 底部一条强调色进度条，暗示"转换"
    bar_y = int(s * 0.80)
    d.rounded_rectangle([int(s * 0.22), bar_y, int(s * 0.78), bar_y + int(s * 0.075)],
                        radius=int(s * 0.04), fill=(255, 255, 255, 90))
    d.rounded_rectangle([int(s * 0.22), bar_y, int(s * 0.58), bar_y + int(s * 0.075)],
                        radius=int(s * 0.04), fill=ACCENT + (255,))

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [render(n) for n in sizes]

    png = OUT_DIR / "icon.png"
    frames[-1].save(png)
    ico = OUT_DIR / "icon.ico"
    frames[-1].save(ico, format="ICO", sizes=[(n, n) for n in sizes])
    print(f"已生成 {png}  {png.stat().st_size:,} bytes")
    print(f"已生成 {ico}  {ico.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
