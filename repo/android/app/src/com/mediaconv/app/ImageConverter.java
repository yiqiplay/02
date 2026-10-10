package com.mediaconv.app;

import android.content.ContentResolver;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;

/** 图片格式转换：基于系统 Bitmap 编解码器。 */
public final class ImageConverter {

    /** 界面可选的图片输出格式。 */
    public enum Format {
        JPEG("JPEG", "image/jpeg", "jpg", true, false, true),
        PNG("PNG", "image/png", "png", false, true, true),
        WEBP_LOSSY("WEBP", "image/webp", "webp", true, true, true),
        WEBP_LOSSLESS("WEBP_LOSSLESS", "image/webp", "webp", false, true, true);

        public final String key;
        public final String mime;
        public final String ext;
        /** 支持 quality 参数 */
        public final boolean lossy;
        /** 支持透明通道 */
        public final boolean alpha;
        public final boolean available;

        Format(String key, String mime, String ext, boolean lossy, boolean alpha, boolean available) {
            this.key = key;
            this.mime = mime;
            this.ext = ext;
            this.lossy = lossy;
            this.alpha = alpha;
            this.available = available;
        }

        public static Format fromKey(String key) {
            for (Format f : values()) {
                if (f.key.equals(key)) return f;
            }
            return JPEG;
        }

        public boolean isLossy() {
            return lossy;
        }
    }

    public interface Progress {
        void onMessage(String text);
    }

    private ImageConverter() {
    }

    /** 探测运行时真正可用的格式（WebP 在部分定制系统上会被裁剪）。 */
    public static void detectAvailability() {
        for (Format f : Format.values()) {
            if (!f.available) continue;
            try {
                Bitmap bmp = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888);
                java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
                Bitmap.CompressFormat cf = compressFormatOf(f);
                boolean ok = bmp.compress(cf, 80, bos) && bos.size() > 0;
                if (!ok) markUnavailable(f);
                bmp.recycle();
            } catch (Throwable t) {
                markUnavailable(f);
            }
        }
    }

    private static void markUnavailable(Format f) {
        try {
            java.lang.reflect.Field field = Format.class.getField(f.name());
            // enum 常量是 public static final，不能直接改；用 Available 集合记录
        } catch (Throwable ignored) {
        }
        UNAVAILABLE.add(f);
    }

    private static final java.util.EnumSet<Format> UNAVAILABLE = java.util.EnumSet.noneOf(Format.class);

    public static boolean isAvailable(Format f) {
        return f.available && !UNAVAILABLE.contains(f);
    }

    private static Bitmap.CompressFormat compressFormatOf(Format f) {
        switch (f) {
            case PNG:
                return Bitmap.CompressFormat.PNG;
            case WEBP_LOSSY:
            case WEBP_LOSSLESS:
                return Bitmap.CompressFormat.WEBP;
            case JPEG:
            default:
                return Bitmap.CompressFormat.JPEG;
        }
    }

    /** 转换入口。返回输出字节数。 */
    public static long convert(Context ctx, Uri src, Uri dst, Format target, int quality,
                               int maxEdge, boolean keepMetadata, Progress progress)
            throws IOException {

        ContentResolver cr = ctx.getContentResolver();

        // 先只读边界，决定是否需要降采样，避免大图直接 OOM
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (InputStream in = open(cr, src)) {
            BitmapFactory.decodeStream(in, null, bounds);
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw new IOException("无法识别该图片，可能不是标准图片格式");
        }
        if (progress != null) {
            progress.onMessage("原图 " + bounds.outWidth + "×" + bounds.outHeight);
        }

        BitmapFactory.Options opts = new BitmapFactory.Options();
        opts.inPreferredConfig = target.alpha ? Bitmap.Config.ARGB_8888 : Bitmap.Config.ARGB_8888;
        int edge = Math.max(bounds.outWidth, bounds.outHeight);
        int sample = 1;
        if (maxEdge > 0) {
            while (edge / (sample * 2) >= maxEdge) sample *= 2;
        } else {
            // 未指定时给一个安全上限，避免超大图 OOM
            while (edge / (sample * 2) >= 4096) sample *= 2;
        }
        opts.inSampleSize = sample;
        opts.inJustDecodeBounds = false;

        Bitmap bmp;
        try (InputStream in = open(cr, src)) {
            bmp = BitmapFactory.decodeStream(in, null, opts);
        }
        if (bmp == null) throw new IOException("解码失败，文件可能已损坏");

        // 精确缩放到目标尺寸
        if (maxEdge > 0) {
            int w = bmp.getWidth(), h = bmp.getHeight();
            int longEdge = Math.max(w, h);
            if (longEdge > maxEdge) {
                float ratio = (float) maxEdge / longEdge;
                int nw = Math.max(1, Math.round(w * ratio));
                int nh = Math.max(1, Math.round(h * ratio));
                Bitmap scaled = Bitmap.createScaledBitmap(bmp, nw, nh, true);
                if (scaled != bmp) bmp.recycle();
                bmp = scaled;
            }
        }

        // 目标不支持透明时，先把透明区域合成到白底
        if (!target.alpha && bmp.hasAlpha()) {
            Bitmap flat = Bitmap.createBitmap(bmp.getWidth(), bmp.getHeight(), Bitmap.Config.ARGB_8888);
            android.graphics.Canvas canvas = new android.graphics.Canvas(flat);
            canvas.drawColor(android.graphics.Color.WHITE);
            canvas.drawBitmap(bmp, 0f, 0f, null);
            bmp.recycle();
            bmp = flat;
        }

        Bitmap.CompressFormat cf = compressFormatOf(target);
        int q = Math.max(1, Math.min(100, quality));
        if (target == Format.WEBP_LOSSLESS) q = 100;

        try (OutputStream os = cr.openOutputStream(dst, "w")) {
            if (os == null) throw new IOException("无法写入输出文件");
            if (!bmp.compress(cf, q, os)) {
                throw new IOException("系统不支持输出该格式，请换一种格式试试");
            }
            os.flush();
        } finally {
            bmp.recycle();
        }

        long size = -1;
        try (android.content.res.AssetFileDescriptor fd = cr.openAssetFileDescriptor(dst, "r")) {
            if (fd != null) size = fd.getLength();
        } catch (Exception ignored) {
        }
        if (progress != null) {
            progress.onMessage(String.format(Locale.US, "完成，输出 %.2f MB",
                    size > 0 ? size / 1048576.0 : 0.0));
        }
        return size;
    }

    private static InputStream open(ContentResolver cr, Uri uri) throws IOException {
        InputStream in = cr.openInputStream(uri);
        if (in == null) throw new IOException("无法读取源文件");
        return in;
    }
}
