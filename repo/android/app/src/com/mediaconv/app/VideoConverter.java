package com.mediaconv.app;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMetadataRetriever;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Build;
import android.util.Log;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 视频 / 音频转码：MediaExtractor 拆包 -> MediaCodec 硬解 -> 缩放 -> MediaCodec 硬编 -> MediaMuxer 封装。
 *
 * 输出格式不是写死的：启动时向 MediaCodecList 查询本机真实支持的编码器，
 * 只有确实能用的组合才会出现在界面里（避免"选了却转不动"）。
 * 音频轨单独解码为 PCM 后再编码。
 */
public final class VideoConverter {

    private static final String TAG = "VideoConverter";
    private static final int TIMEOUT_US = 10_000;
    /** 编码器迟迟不返回 EOS 时的兜底等待时间 */
    private static final long EOS_TIMEOUT_MS = 8000;

    // ------------------------------------------------------------------ 目标格式

    /** 输出组合：容器 + 视频编码 + 音频编码。 */
    public enum Target {
        MP4_H264("MP4 · H.264（兼容性最好）", "mp4", "video/mp4",
                MediaFormat.MIMETYPE_VIDEO_AVC, MediaFormat.MIMETYPE_AUDIO_AAC, true),
        MP4_HEVC("MP4 · H.265（体积小约 40%）", "mp4", "video/mp4",
                MediaFormat.MIMETYPE_VIDEO_HEVC, MediaFormat.MIMETYPE_AUDIO_AAC, true),
        WEBM_VP8("WebM · VP8（网页通用）", "webm", "video/webm",
                MediaFormat.MIMETYPE_VIDEO_VP8, MediaFormat.MIMETYPE_AUDIO_OPUS, true),
        WEBM_VP9("WebM · VP9（压缩率更高）", "webm", "video/webm",
                MediaFormat.MIMETYPE_VIDEO_VP9, MediaFormat.MIMETYPE_AUDIO_OPUS, true),
        AUDIO_M4A("只要音频 · M4A（AAC）", "m4a", "audio/mp4",
                null, MediaFormat.MIMETYPE_AUDIO_AAC, false),
        AUDIO_AAC("只要音频 · AAC", "aac", "audio/aac",
                null, MediaFormat.MIMETYPE_AUDIO_AAC, false);

        public final String label;
        public final String ext;
        public final String mime;
        public final String videoMime;   // null 表示纯音频
        public final String audioMime;
        public final boolean hasVideo;

        Target(String label, String ext, String mime, String videoMime, String audioMime, boolean hasVideo) {
            this.label = label;
            this.ext = ext;
            this.mime = mime;
            this.videoMime = videoMime;
            this.audioMime = audioMime;
            this.hasVideo = hasVideo;
        }

        public static Target fromKey(String key) {
            for (Target t : values()) {
                if (t.name().equals(key)) return t;
            }
            return MP4_H264;
        }
    }

    /** 输出分辨率档位。 */
    public enum Scale {
        KEEP("保持原始分辨率", 0),
        P2160("4K 2160p", 2160),
        P1440("2K 1440p", 1440),
        P1080("1080p", 1080),
        P720("720p", 720),
        P480("480p", 480),
        P360("360p", 360);

        public final String label;
        public final int height;

        Scale(String label, int height) {
            this.label = label;
            this.height = height;
        }

        public static Scale fromKey(String key) {
            for (Scale s : values()) {
                if (s.name().equals(key)) return s;
            }
            return KEEP;
        }
    }

    // ------------------------------------------------------------------ 能力探测

    private static List<String> sEncoderMimes;

    /** 收集本机所有编码器 mime（缓存一次）。 */
    private static synchronized List<String> encoderMimes() {
        if (sEncoderMimes == null) {
            List<String> list = new ArrayList<>();
            try {
                MediaCodecList all = new MediaCodecList(MediaCodecList.ALL_CODECS);
                for (MediaCodecInfo info : all.getCodecInfos()) {
                    if (!info.isEncoder()) continue;
                    for (String mime : info.getSupportedTypes()) {
                        String m = mime.toLowerCase(Locale.US);
                        if (!list.contains(m)) list.add(m);
                    }
                }
            } catch (Throwable t) {
                Log.w(TAG, "cannot enumerate encoders", t);
            }
            sEncoderMimes = list;
        }
        return sEncoderMimes;
    }

    /** 某个目标格式在本机是否可用。 */
    public static boolean isTargetAvailable(Target t) {
        List<String> mimes = encoderMimes();
        boolean audioOk = mimes.contains(t.audioMime.toLowerCase(Locale.US));
        if (!audioOk) return false;
        if (t.videoMime == null) return true;
        return mimes.contains(t.videoMime.toLowerCase(Locale.US));
    }

    /** 本机可用的目标格式列表（至少保证 MP4/H.264 在列）。 */
    public static List<Target> availableTargets() {
        List<Target> out = new ArrayList<>();
        for (Target t : Target.values()) {
            if (isTargetAvailable(t)) out.add(t);
        }
        if (out.isEmpty()) out.add(Target.MP4_H264);
        return out;
    }

    /** 供界面显示的探测摘要。 */
    public static String capabilitySummary() {
        List<Target> avail = availableTargets();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < avail.size(); i++) {
            if (i > 0) sb.append(" / ");
            sb.append(avail.get(i).label);
        }
        return sb.toString();
    }

    // ------------------------------------------------------------------ 回调与结果

    public interface Callback {
        /** @param fraction 0..1，未知时为 -1 */
        void onProgress(double fraction, String stage, String detail);

        boolean isCancelled();
    }

    public static final class Result {
        public boolean ok;
        public boolean hasVideo;
        public boolean hasAudio;
        public long bytes;
        public int outWidth;
        public int outHeight;
        public double durationSec;
        public String message = "";
        public String warning = "";
    }

    public static final class Options {
        public Target target = Target.MP4_H264;
        public Scale scale = Scale.KEEP;
        public int maxFps = 0;              // 0 = 保持原始
        public int crfLikeQuality = 23;     // 1..51，越小越清晰
        public boolean includeAudio = true;
        public long trimStartUs = 0;
        public long trimEndUs = 0;          // 0 = 到结尾
    }

    private VideoConverter() {
    }

    /** 读取媒体基本信息，用于界面显示。 */
    public static String describe(Context ctx, Uri uri) {
        MediaMetadataRetriever r = new MediaMetadataRetriever();
        try {
            r.setDataSource(ctx, uri);
            String w = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH);
            String h = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT);
            String dur = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            String br = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE);
            StringBuilder sb = new StringBuilder();
            if (w != null && h != null) sb.append(w).append("×").append(h);
            if (dur != null) {
                long ms = Long.parseLong(dur);
                if (sb.length() > 0) sb.append(" · ");
                sb.append(String.format(Locale.US, "%d:%02d", ms / 60000, (ms / 1000) % 60));
            }
            if (br != null) {
                if (sb.length() > 0) sb.append(" · ");
                sb.append(String.format(Locale.US, "%.1f Mbps", Long.parseLong(br) / 1_000_000.0));
            }
            return sb.toString();
        } catch (Throwable t) {
            return "";
        } finally {
            try {
                r.release();
            } catch (Throwable ignored) {
            }
        }
    }

    // ------------------------------------------------------------------ 主流程

    public static Result convert(Context ctx, Uri src, String dstPath,
                                 Options opt, Callback cb) throws IOException {
        Result res = new Result();
        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;
        MediaCodec vDec = null, vEnc = null, aDec = null, aEnc = null;
        boolean muxerStarted = false;

        try {
            extractor.setDataSource(ctx, src, null);

            int vTrack = -1, aTrack = -1;
            MediaFormat vFmt = null, aFmt = null;
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                MediaFormat f = extractor.getTrackFormat(i);
                String mime = f.getString(MediaFormat.KEY_MIME);
                if (mime == null) continue;
                if (mime.startsWith("video/") && vTrack < 0) {
                    vTrack = i;
                    vFmt = f;
                } else if (mime.startsWith("audio/") && aTrack < 0) {
                    aTrack = i;
                    aFmt = f;
                }
            }

            boolean wantVideo = opt.target.hasVideo;
            if (vTrack < 0 && aTrack < 0) {
                res.message = "文件里没有找到视频或音频轨";
                return res;
            }
            if (wantVideo && vTrack < 0) {
                res.message = "这个文件没有视频轨，请选择「只要音频」的目标格式";
                return res;
            }

            long durationUs = 0;
            if (vFmt != null && vFmt.containsKey(MediaFormat.KEY_DURATION)) {
                durationUs = vFmt.getLong(MediaFormat.KEY_DURATION);
            } else if (aFmt != null && aFmt.containsKey(MediaFormat.KEY_DURATION)) {
                durationUs = aFmt.getLong(MediaFormat.KEY_DURATION);
            }
            res.durationSec = durationUs / 1_000_000.0;

            int muxerFormat = "webm".equals(opt.target.ext)
                    ? MediaMuxer.OutputFormat.MUXER_OUTPUT_WEBM
                    : MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4;
            muxer = new MediaMuxer(dstPath, muxerFormat);
            if (vTrack >= 0 && wantVideo) {
                muxer.setOrientationHint(readRotation(ctx, src));
            }

            // ---------------- 视频轨 ----------------
            if (wantVideo && vTrack >= 0) {
                MediaFormat outFmt = prepareVideoEncoder(vFmt, opt, res);
                vEnc = MediaCodec.createEncoderByType(opt.target.videoMime);
                vEnc.configure(outFmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);

                vDec = MediaCodec.createDecoderByType(vFmt.getString(MediaFormat.KEY_MIME));
                vDec.configure(vFmt, vEnc.createInputSurface(), null, 0);

                vDec.start();
                vEnc.start();

                boolean ok = transcodeVideo(extractor, vTrack, vDec, vEnc, muxer, opt, res, cb);
                if (cb != null && cb.isCancelled()) {
                    res.message = "已取消";
                    return res;
                }
                if (!ok) {
                    res.message = "视频轨转码失败，请换一种目标格式试试";
                    return res;
                }
                muxerStarted = true;
                res.hasVideo = true;
            }

            // ---------------- 音频轨 ----------------
            if (aTrack >= 0 && opt.includeAudio) {
                try {
                    aDec = MediaCodec.createDecoderByType(aFmt.getString(MediaFormat.KEY_MIME));
                    aDec.configure(aFmt, null, null, 0);
                    aDec.start();

                    aEnc = MediaCodec.createEncoderByType(opt.target.audioMime);
                    aEnc.configure(makeAudioFormat(opt), null, null,
                            MediaCodec.CONFIGURE_FLAG_ENCODE);
                    aEnc.start();

                    transcodeAudio(extractor, aTrack, aDec, aEnc, muxer, muxerStarted, opt, cb);
                    res.hasAudio = true;
                } catch (Throwable t) {
                    Log.w(TAG, "audio transcode failed", t);
                    if (!wantVideo) {
                        // 纯音频目标失败就没有任何内容可写了
                        res.message = "音频转码失败：" + (t.getMessage() == null ? t.toString() : t.getMessage());
                        return res;
                    }
                    res.warning = "音频轨未能转换，输出为无声视频";
                }
            }

            if (muxerStarted) {
                muxer.stop();
            }
            res.ok = true;
            if (res.message.isEmpty()) res.message = "完成";
            return res;

        } finally {
            closeQuietly(vDec);
            closeQuietly(vEnc);
            closeQuietly(aDec);
            closeQuietly(aEnc);
            if (muxer != null) {
                try {
                    muxer.release();
                } catch (Throwable ignored) {
                }
            }
            try {
                extractor.release();
            } catch (Throwable ignored) {
            }
        }
    }

    // ------------------------------------------------------------------ 视频

    private static MediaFormat prepareVideoEncoder(MediaFormat srcFmt, Options opt, Result res) {
        int srcW = srcFmt.getInteger(MediaFormat.KEY_WIDTH);
        int srcH = srcFmt.getInteger(MediaFormat.KEY_HEIGHT);
        int rotation = srcFmt.containsKey("rotation-degrees")
                ? srcFmt.getInteger("rotation-degrees") : 0;
        if (rotation == 90 || rotation == 270) {
            int t = srcW;
            srcW = srcH;
            srcH = t;
        }

        int outW = srcW, outH = srcH;
        if (opt.scale.height > 0 && srcH > opt.scale.height) {
            double ratio = (double) opt.scale.height / srcH;
            outW = (int) Math.round(srcW * ratio);
            outH = opt.scale.height;
        }
        // H.264 / H.265 / VP8 / VP9 都要求宽高为偶数
        outW = Math.max(2, outW & ~1);
        outH = Math.max(2, outH & ~1);

        int srcFps = 30;
        try {
            if (srcFmt.containsKey(MediaFormat.KEY_FRAME_RATE)) {
                srcFps = Math.max(1, srcFmt.getInteger(MediaFormat.KEY_FRAME_RATE));
            }
        } catch (Throwable ignored) {
        }
        int fps = opt.maxFps > 0 ? Math.min(opt.maxFps, srcFps) : srcFps;

        // 码率参考：比特/像素 起步系数。
        // H.265 / VP9 同画质只需 H.264 的约 60%，所以给更低的系数。
        double bpp = 0.09;
        if (MediaFormat.MIMETYPE_VIDEO_HEVC.equals(opt.target.videoMime)
                || MediaFormat.MIMETYPE_VIDEO_VP9.equals(opt.target.videoMime)) {
            bpp = 0.06;
        } else if (MediaFormat.MIMETYPE_VIDEO_VP8.equals(opt.target.videoMime)) {
            bpp = 0.10;
        }
        bpp *= (1.0 + (28 - opt.crfLikeQuality) * 0.03);

        int bitrate = (int) Math.max(600_000,
                Math.min(40_000_000L, (long) (outW * outH * fps * bpp)));
        int iframe = Math.max(1, fps);

        MediaFormat out = MediaFormat.createVideoFormat(opt.target.videoMime, outW, outH);
        out.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        out.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        out.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        out.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, iframe);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            out.setInteger(MediaFormat.KEY_BITRATE_MODE,
                    MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR);
        }

        res.outWidth = outW;
        res.outHeight = outH;
        return out;
    }

    private static boolean transcodeVideo(MediaExtractor extractor, int track,
                                          MediaCodec dec, MediaCodec enc, MediaMuxer muxer,
                                          Options opt, Result res, Callback cb) {
        extractor.selectTrack(track);
        if (opt.trimStartUs > 0) extractor.seekTo(opt.trimStartUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC);

        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        boolean decEos = false, encEos = false, eosSignaled = false;
        int muxTrack = -1;
        long frames = 0;
        long startUs = opt.trimStartUs;
        long durationUs = (long) (res.durationSec * 1_000_000L);
        long lastPtsUs = 0;
        long eosDeadline = 0;

        while (!encEos) {
            if (cb != null && cb.isCancelled()) return false;

            // 兜底：个别设备在 signalEndOfInputStream 后迟迟不返回 EOS
            if (eosSignaled) {
                if (eosDeadline == 0) {
                    eosDeadline = System.currentTimeMillis() + EOS_TIMEOUT_MS;
                } else if (System.currentTimeMillis() > eosDeadline) {
                    Log.w(TAG, "encoder EOS timeout; stopping with " + frames + " frames");
                    break;
                }
            }

            // ---- 喂给解码器 ----
            if (!decEos) {
                int inIdx = dec.dequeueInputBuffer(TIMEOUT_US);
                if (inIdx >= 0) {
                    ByteBuffer buf = dec.getInputBuffer(inIdx);
                    int size = extractor.readSampleData(buf, 0);
                    long pts = extractor.getSampleTime();
                    if (size < 0 || (opt.trimEndUs > 0 && pts > opt.trimEndUs)) {
                        dec.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                        decEos = true;
                    } else {
                        dec.queueInputBuffer(inIdx, 0, size, pts, 0);
                        extractor.advance();
                    }
                }
            }

            // ---- 解码输出 -> 编码器输入 Surface ----
            int outIdx = dec.dequeueOutputBuffer(info, TIMEOUT_US);
            if (outIdx >= 0) {
                boolean eos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                dec.releaseOutputBuffer(outIdx, info.size > 0);
                if (info.size > 0) {
                    lastPtsUs = info.presentationTimeUs;
                    frames++;
                }
                if (eos) {
                    decEos = true;
                    // 显式告诉编码器没有更多帧，否则部分设备不吐最后几帧
                    enc.signalEndOfInputStream();
                    eosSignaled = true;
                }

                if (frames > 0 && cb != null && durationUs > 0 && frames % 10 == 0) {
                    double frac = Math.min(0.99, (lastPtsUs - startUs) / (double) durationUs);
                    cb.onProgress(frac, "转码中",
                            String.format(Locale.US, "已处理 %d 帧 · %.0f%%", frames, frac * 100));
                }
            }

            // ---- 取出编码结果 ----
            int encIdx = enc.dequeueOutputBuffer(info, TIMEOUT_US);
            if (encIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                muxTrack = muxer.addTrack(enc.getOutputFormat());
                muxer.start();
            } else if (encIdx >= 0) {
                ByteBuffer buf = enc.getOutputBuffer(encIdx);
                if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                    info.size = 0;
                }
                if (info.size > 0 && buf != null && muxTrack >= 0) {
                    buf.position(info.offset);
                    buf.limit(info.offset + info.size);
                    muxer.writeSampleData(muxTrack, buf, info);
                }
                boolean eos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                enc.releaseOutputBuffer(encIdx, false);
                if (eos) encEos = true;
            }
        }
        res.hasVideo = frames > 0;
        return frames > 0;
    }

    // ------------------------------------------------------------------ 音频

    private static MediaFormat makeAudioFormat(Options opt) {
        boolean opus = MediaFormat.MIMETYPE_AUDIO_OPUS.equals(opt.target.audioMime);
        // Opus 只能 48kHz；AAC 用 48kHz 也最稳妥
        MediaFormat out = MediaFormat.createAudioFormat(opt.target.audioMime, 48000, 2);
        out.setInteger(MediaFormat.KEY_BIT_RATE, 128_000);
        if (!opus) {
            out.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
        }
        out.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 65536);
        return out;
    }

    private static void transcodeAudio(MediaExtractor extractor, int track,
                                       MediaCodec dec, MediaCodec enc, MediaMuxer muxer,
                                       boolean muxerStarted, Options opt, Callback cb) {
        extractor.selectTrack(track);
        extractor.seekTo(0, MediaExtractor.SEEK_TO_PREVIOUS_SYNC);

        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        boolean decEos = false, encEos = false;
        int muxTrack = -1;
        long stamp = 0;
        long deadline = 0;

        while (!encEos) {
            if (cb != null && cb.isCancelled()) return;
            if (decEos) {
                if (deadline == 0) deadline = System.currentTimeMillis() + EOS_TIMEOUT_MS;
                else if (System.currentTimeMillis() > deadline) break;
            }

            if (!decEos) {
                int inIdx = dec.dequeueInputBuffer(TIMEOUT_US);
                if (inIdx >= 0) {
                    ByteBuffer buf = dec.getInputBuffer(inIdx);
                    int size = extractor.readSampleData(buf, 0);
                    long pts = extractor.getSampleTime();
                    if (size < 0 || (opt.trimEndUs > 0 && pts > opt.trimEndUs)) {
                        dec.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                        decEos = true;
                    } else {
                        dec.queueInputBuffer(inIdx, 0, size, pts, 0);
                        extractor.advance();
                    }
                }
            }

            int outIdx = dec.dequeueOutputBuffer(info, TIMEOUT_US);
            if (outIdx >= 0) {
                ByteBuffer pcm = dec.getOutputBuffer(outIdx);
                if (pcm != null && info.size > 0) {
                    // 用单调递增的时间戳：seek 之后原始时间戳可能回退，
                    // 会让 muxer 直接报错，所以这里自己算。
                    feedEncoder(enc, pcm, info, stamp);
                    stamp += 21_333;   // 约 1024 采样 @48kHz
                }
                dec.releaseOutputBuffer(outIdx, false);
                if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) decEos = true;
            }

            int encIdx = enc.dequeueOutputBuffer(info, TIMEOUT_US);
            if (encIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                muxTrack = muxer.addTrack(enc.getOutputFormat());
                if (!muxerStarted) muxer.start();
            } else if (encIdx >= 0) {
                ByteBuffer buf = enc.getOutputBuffer(encIdx);
                if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) info.size = 0;
                if (info.size > 0 && buf != null && muxTrack >= 0) {
                    buf.position(info.offset);
                    buf.limit(info.offset + info.size);
                    muxer.writeSampleData(muxTrack, buf, info);
                }
                boolean eos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                enc.releaseOutputBuffer(encIdx, false);
                if (eos) encEos = true;
            }
        }
    }

    private static void feedEncoder(MediaCodec enc, ByteBuffer pcm, MediaCodec.BufferInfo info, long stamp) {
        int inIdx = enc.dequeueInputBuffer(TIMEOUT_US);
        if (inIdx < 0) return;
        ByteBuffer dst = enc.getInputBuffer(inIdx);
        if (dst == null) return;
        dst.clear();
        pcm.position(info.offset);
        pcm.limit(info.offset + info.size);
        dst.put(pcm);
        enc.queueInputBuffer(inIdx, 0, info.size, stamp, 0);
    }

    // ------------------------------------------------------------------ 工具

    private static int readRotation(Context ctx, Uri uri) {
        MediaMetadataRetriever r = new MediaMetadataRetriever();
        try {
            r.setDataSource(ctx, uri);
            String rot = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION);
            return rot == null ? 0 : Integer.parseInt(rot);
        } catch (Throwable t) {
            return 0;
        } finally {
            try {
                r.release();
            } catch (Throwable ignored) {
            }
        }
    }

    private static void closeQuietly(MediaCodec codec) {
        if (codec == null) return;
        try {
            codec.stop();
        } catch (Throwable ignored) {
        }
        try {
            codec.release();
        } catch (Throwable ignored) {
        }
    }
}
