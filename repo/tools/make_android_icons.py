"""生成 Android 各密度图标（mipmap-*dpi/ic_launcher.png）。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "android" / "app" / "res"

# mdpi / hdpi / xhdpi / xxhdpi / xxxhdpi 对应的启动图标边长
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def main() -> int:
    sys.path.insert(0, str(HERE))
    from make_icon import render  # 复用桌面版图标绘制

    for folder, size in DENSITIES.items():
        d = RES / folder
        d.mkdir(parents=True, exist_ok=True)
        img = render(size)
        # Android 启动图标自带圆角遮罩，所以这里补上不透明底色避免边缘发灰
        flat = Image.new("RGBA", img.size, (28, 110, 200, 255))
        flat.alpha_composite(img)
        out = d / "ic_launcher.png"
        flat.save(out)
        print(f"  {folder:<16} {size}x{size}  {out.stat().st_size:,} bytes")

    print(f"已生成 {len(DENSITIES)} 个密度的图标 -> {RES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
