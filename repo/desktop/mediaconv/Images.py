"""图片转换引擎：基于 Pillow（含 HEIC / AVIF 插件）。

注意：视频类容器（含 GIF→MP4 这类）不在本模块处理，交给 FFmpeg 通道。
本模块只负责"静态图 / 多帧图 → 图片格式"。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import Formats

# HEIC/HEIF 与 AVIF 的注册统一由 Formats 负责，避免两处状态不一致
PluginStatus = Formats.register_image_plugins()
_HEIF_OK = PluginStatus.get("heif", False)
_AVIF_OK = PluginStatus.get("avif", False)


class ImageConvertError(RuntimeError):
    pass


@dataclass
class ImageOptions:
    """图片转换参数。"""

    target_key: str = "JPEG"        # Formats.ImageFormat.key
    quality: int = 90               # 1-100
    keep_metadata: bool = False     # 是否保留 EXIF 等
    resize_mode: str = "none"       # none | percent | width | height | max | exact
    resize_value: float = 100.0     # percent 时是百分比
    resize_value2: float = 0.0      # exact 模式下的高度
    background: str = "#FFFFFF"     # 透明背景填充色（目标格式不支持透明时）
    optimize: bool = True
    target_ext: str | None = None   # 覆盖扩展名（如 APNG 用 .apng 但 Pillow 格式是 PNG）


@dataclass
class ImageConvertResult:
    output: Path
    frames: int = 1
    in_size: int = 0
    out_size: int = 0
    width: int = 0
    height: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ratio_text(self) -> str:
        if not self.in_size or not self.out_size:
            return ""
        delta = (self.out_size - self.in_size) / self.in_size * 100
        return f"{delta:+.1f}%"


def _hex_to_rgb(text: str) -> tuple[int, int, int]:
    t = (text or "#FFFFFF").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    try:
        return (int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16))
    except (ValueError, IndexError):
        return (255, 255, 255)


def _target_format(key: str) -> Formats.ImageFormat:
    for f in Formats.available_image_formats():
        if f.key == key:
            return f
    raise ImageConvertError(f"本机 Pillow 不支持输出格式：{key}")


def _compute_size(w: int, h: int, opt: ImageOptions) -> tuple[int, int]:
    mode = opt.resize_mode
    v = float(opt.resize_value or 0)
    if mode == "none" or v <= 0:
        return w, h
    if mode == "percent":
        scale = v / 100.0
        return max(1, round(w * scale)), max(1, round(h * scale))
    if mode == "width":
        scale = v / w
        return max(1, round(v)), max(1, round(h * scale))
    if mode == "height":
        scale = v / h
        return max(1, round(w * scale)), max(1, round(v))
    if mode == "max":
        scale = min(1.0, v / max(w, h))
        return max(1, round(w * scale)), max(1, round(h * scale))
    if mode == "exact":
        return max(1, round(v)), max(1, round(float(opt.resize_value2 or v)))
    return w, h


def _flatten_alpha(img, bg: tuple[int, int, int]):
    """把带透明通道的图合成到纯色背景上。"""
    from PIL import Image

    if img.mode in ("RGBA", "LA", "PA"):
        base = Image.new("RGB", img.size, bg)
        alpha = img.convert("RGBA")
        base.paste(alpha, mask=alpha.split()[-1])
        return base
    if img.mode == "P" and "transparency" in img.info:
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, bg)
        base.paste(rgba, mask=rgba.split()[-1])
        return base
    return img


def _prepare_frame(img, target: Formats.ImageFormat, opt: ImageOptions):
    """按目标格式要求调整色彩模式。"""
    from PIL import Image

    if target.supports_alpha:
        if img.mode not in ("RGBA", "LA", "P", "RGB", "L"):
            img = img.convert("RGBA")
        elif img.mode in ("CMYK", "I;16", "F", "1"):
            img = img.convert("RGBA")
        return img

    # 目标不支持透明：填背景色
    img = _flatten_alpha(img, _hex_to_rgb(opt.background))
    if target.key in ("JPEG", "JPEG2000", "PPM", "PCX", "DDS", "PALM"):
        if img.mode != "RGB":
            img = img.convert("RGB")
    elif target.key == "BMP":
        if img.mode not in ("RGB", "L", "P", "RGBA"):
            img = img.convert("RGB")
    elif img.mode not in ("RGB", "L", "P", "1"):
        img = img.convert("RGB")
    return img


def _save_kwargs(target: Formats.ImageFormat, opt: ImageOptions, animated: bool) -> dict:
    kw: dict = {}
    q = max(1, min(100, int(opt.quality)))

    if target.key == "JPEG":
        kw.update(quality=q, optimize=opt.optimize, progressive=True, subsampling=-1 if q >= 95 else 2)
    elif target.key == "PNG":
        # PNG 的"quality"其实是 zlib 压缩级别，映射到 0-9
        kw.update(optimize=opt.optimize, compress_level=max(0, min(9, round((100 - q) / 100 * 9))))
        if animated:
            kw.update(save_all=True, append_images=[], duration=100, loop=0)
    elif target.key in ("WEBP",):
        kw.update(quality=q, method=4)
        if animated:
            kw.update(save_all=True, append_images=[], duration=100, loop=0)
    elif target.key == "AVIF":
        kw.update(quality=q, speed=6)
    elif target.key == "HEIF":
        kw.update(quality=q)
    elif target.key == "JPEG2000":
        kw.update(quality_mode="rates", quality_layers=[max(1, round((100 - q) / 100 * 40) or 1)])
    elif target.key == "GIF":
        kw.update(optimize=opt.optimize)
        if animated:
            kw.update(save_all=True, append_images=[], duration=100, loop=0)
    elif target.key == "TIFF":
        kw.update(compression="tiff_deflate")
        if animated:
            kw.update(save_all=True, append_images=[])
    elif target.key == "ICO":
        kw.update(sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    elif target.key == "PDF":
        kw.update(resolution=150.0, quality=q)
    elif target.key == "DDS":
        pass
    elif target.key in ("BMP", "TGA", "PCX", "PPM", "SGI", "QOI", "XBM", "PALM", "WMF", "MPO"):
        pass
    return kw


def convert_image(src: str | Path, dst: str | Path, opt: ImageOptions) -> ImageConvertResult:
    """执行单张图片转换。"""
    from PIL import Image

    src_p, dst_p = Path(src), Path(dst)
    if not src_p.exists():
        raise ImageConvertError(f"文件不存在：{src_p}")

    target = _target_format(opt.target_key)
    res = ImageConvertResult(output=dst_p, in_size=src_p.stat().st_size)

    try:
        im = Image.open(src_p)
    except Exception as e:  # Pillow 抛的异常类型很杂，统一包装
        raise ImageConvertError(f"无法读取图片（{src_p.name}）：{e}") from e

    exif = None
    if opt.keep_metadata:
        try:
            exif = im.info.get("exif")
        except Exception:
            exif = None

    n_frames = getattr(im, "n_frames", 1)
    want_animated = target.supports_multi and n_frames > 1

    dst_p.parent.mkdir(parents=True, exist_ok=True)
    kw = _save_kwargs(target, opt, want_animated)
    if exif and target.key in ("JPEG", "WEBP", "TIFF", "PNG", "HEIF", "AVIF"):
        kw["exif"] = exif

    try:
        if want_animated:
            frames = []
            durations = []
            for i in range(n_frames):
                im.seek(i)
                fr = im.convert("RGBA") if target.supports_alpha else im.convert("RGB")
                fr = _prepare_frame(fr, target, opt)
                nw, nh = _compute_size(fr.width, fr.height, opt)
                if (nw, nh) != fr.size:
                    fr = fr.resize((nw, nh), Image.LANCZOS)
                frames.append(fr)
                durations.append(im.info.get("duration", 100) or 100)
            res.frames = len(frames)
            res.width, res.height = frames[0].size
            kw["append_images"] = frames[1:]
            kw["duration"] = durations
            kw["loop"] = im.info.get("loop", 0)
            if target.key == "PDF":
                frames[0].save(dst_p, format="PDF", save_all=True, append_images=frames[1:], **kw)
            else:
                frames[0].save(dst_p, format=target.key if target.key != "APNG" else "PNG", **kw)
        else:
            im.seek(0) if n_frames > 1 else None
            frame = im
            frame = _prepare_frame(frame, target, opt)
            nw, nh = _compute_size(frame.width, frame.height, opt)
            if (nw, nh) != frame.size:
                frame = frame.resize((nw, nh), Image.LANCZOS)
            res.width, res.height = frame.size
            frame.save(dst_p, format=target.key if target.key != "APNG" else "PNG", **kw)
    except Exception as e:
        raise ImageConvertError(f"保存失败（{dst_p.name}）：{e}") from e
    finally:
        try:
            im.close()
        except Exception:
            pass

    res.out_size = dst_p.stat().st_size if dst_p.exists() else 0
    if target.key == "JPEG" and dst_p.exists() and dst_p.stat().st_size > 40 * 1024 * 1024:
        res.warnings.append("输出文件超过 40MB，建议降低质量或尺寸")
    return res


def changed_format_only(src: str | Path, opt: ImageOptions) -> bool:
    """判断是否只是换了扩展名（用于跳过无意义转换的提示）。"""
    ext = Path(src).suffix.lower()
    target = _target_format(opt.target_key)
    same = ext in {target.ext, ".jpeg" if target.key == "JPEG" else target.ext}
    no_resize = opt.resize_mode == "none" or not opt.resize_value
    return bool(same and no_resize and opt.keep_metadata)


def suggested_output(src: str | Path, target_key: str, out_dir: str | Path | None = None,
                     suffix: str = "_converted") -> Path:
    """生成输出路径，自动避免覆盖原文件。"""
    src_p = Path(src)
    target = _target_format(target_key)
    ext = target.ext
    stem = src_p.stem
    directory = Path(out_dir) if out_dir else src_p.parent
    candidate = directory / f"{stem}{suffix}{ext}"
    if candidate.resolve() == src_p.resolve():
        candidate = directory / f"{stem}{suffix}{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem}{suffix}_{n}{ext}"
        n += 1
    return candidate


def output_extension(target_key: str, source: str | Path | None = None) -> str:
    """返回目标格式的扩展名（GIF 动图等特殊格式保持自身扩展名）。"""
    return _target_format(target_key).ext


def plugin_status() -> dict[str, bool]:
    return {"heif": _HEIF_OK, "avif": _AVIF_OK}
