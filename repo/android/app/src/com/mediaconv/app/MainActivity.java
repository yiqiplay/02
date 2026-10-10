package com.mediaconv.app;

import android.app.Activity;
import android.app.ProgressDialog;
import android.content.ContentValues;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.text.method.ScrollingMovementMethod;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 单界面 App：选文件 -> 选格式 -> 转换。
 * 不依赖 AndroidX / support 库，纯平台 API，保证离线可编译、体积小。
 */
public class MainActivity extends Activity {

    /** 版本号：与 AndroidManifest 的 versionName 保持一致 */
    public static final String APP_VERSION = "1.0.0";
    /** 开发者 */
    public static final String APP_AUTHOR = "xiaoke";

    private static final int REQ_PICK = 1001;

    private static final String[] IMAGE_EXTS = {
            ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".bmp", ".gif",
            ".heic", ".heif", ".avif", ".tif", ".tiff", ".ico", ".dng", ".wdp"
    };
    private static final String[] VIDEO_EXTS = {
            ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".3gp", ".3g2",
            ".ts", ".m2ts", ".mts", ".flv", ".wmv", ".mpg", ".mpeg", ".vob", ".rm", ".rmvb", ".ogv"
    };
    private static final String[] AUDIO_EXTS = {
            ".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".oga", ".opus", ".amr", ".wma", ".ac3", ".aiff"
    };

    private enum Kind {IMAGE, VIDEO, AUDIO, UNKNOWN}

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService pool = Executors.newSingleThreadExecutor();

    private TextView tvFile, tvInfo, tvStatus;
    private Spinner spImageTarget, spVideoTarget, spVideoScale, spVideoQuality, spImageEdge;
    private CheckBox cbKeepAudio;
    private SeekBar sbQuality;
    private TextView tvQualityLabel;
    private RadioGroup rgMode;
    private RadioButton rbImage, rbVideo;
    private LinearLayout boxImage, boxVideo;
    private Button btnPick, btnConvert, btnOpen;
    private DragScrollView scrollView;

    /** 本机真实可用的目标格式（启动时探测）。 */
    private List<VideoConverter.Target> videoTargets = new ArrayList<>();
    private List<ImageConverter.Format> imageTargets = new ArrayList<>();

    private Uri srcUri;
    private String srcName = "";
    private Kind srcKind = Kind.UNKNOWN;
    private Uri lastOutput;
    private volatile boolean cancelled = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ImageConverter.detectAvailability();
        videoTargets = VideoConverter.availableTargets();
        imageTargets = availableImageFormats();
        setContentView(buildUi());
        updateForKind();
        handleIncomingIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIncomingIntent(intent);
    }

    /** 支持从相册「打开方式」或分享菜单直接带文件进来。 */
    private void handleIncomingIntent(Intent intent) {
        if (intent == null) return;
        Uri uri = null;
        String action = intent.getAction();
        if (Intent.ACTION_VIEW.equals(action)) {
            uri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(action)) {
            Object extra = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (extra instanceof Uri) uri = (Uri) extra;
        }
        if (uri == null) return;

        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Throwable ignored) {
        }
        srcUri = uri;
        srcName = queryName(uri);
        srcKind = kindOf(srcName);
        tvFile.setText(srcName);
        if (srcKind == Kind.IMAGE) {
            rbImage.setChecked(true);
        } else if (srcKind == Kind.VIDEO || srcKind == Kind.AUDIO) {
            rbVideo.setChecked(true);
        }
        updateForKind();
        probeInfo();
    }

    // ------------------------------------------------------------------ 界面

    private View buildUi() {
        // 用自定义的 DragScrollView 代替原生 ScrollView：
        // 原生实现在"纯代码构建视图"时实测无法响应拖动，这个类显式接管了触控。
        final DragScrollView scroll = new DragScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#F5F6F8"));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(14);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root, new android.widget.FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        // 标题行（右上角放「说明」按钮，把冗长文字从主界面挪进弹窗，
        // 这样主界面在常见手机上一屏就能放下，不依赖滚动也能用）
        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setOrientation(LinearLayout.HORIZONTAL);
        titleRow.setGravity(android.view.Gravity.CENTER_VERTICAL);

        TextView title = new TextView(this);
        title.setText("格式转换器");
        title.setTextSize(20);
        title.setTextColor(Color.parseColor("#1B1D21"));
        titleRow.addView(title, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button btnHelp = new Button(this);
        btnHelp.setText("说明");
        btnHelp.setAllCaps(false);
        btnHelp.setTextSize(13);
        btnHelp.setOnClickListener(v -> showHelp());
        titleRow.addView(btnHelp, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        root.addView(titleRow);

        TextView sub = new TextView(this);
        sub.setText("图片 · 视频 · 音频　本地转换，不联网、不上传");
        sub.setTextSize(12);
        sub.setTextColor(Color.parseColor("#6B7280"));
        sub.setPadding(0, dp(2), 0, dp(10));
        root.addView(sub);

        // 选择文件卡片
        LinearLayout fileCard = card();
        btnPick = new Button(this);
        btnPick.setText("选择文件");
        btnPick.setAllCaps(false);
        btnPick.setOnClickListener(v -> pickFile());
        fileCard.addView(btnPick);

        tvFile = new TextView(this);
        tvFile.setText("还没有选择文件");
        tvFile.setTextSize(14);
        tvFile.setTextColor(Color.parseColor("#374151"));
        tvFile.setPadding(0, dp(10), 0, 0);
        fileCard.addView(tvFile);

        tvInfo = new TextView(this);
        tvInfo.setTextSize(12);
        tvInfo.setTextColor(Color.parseColor("#6B7280"));
        tvInfo.setPadding(0, dp(4), 0, 0);
        fileCard.addView(tvInfo);
        root.addView(fileCard);

        // 模式选择
        rgMode = new RadioGroup(this);
        rgMode.setOrientation(RadioGroup.HORIZONTAL);
        rbImage = new RadioButton(this);
        rbImage.setText("图片转换");
        rbImage.setId(View.generateViewId());
        rbVideo = new RadioButton(this);
        rbVideo.setText("视频/音频转换");
        rbVideo.setId(View.generateViewId());
        rgMode.addView(rbImage);
        rgMode.addView(rbVideo);
        rbVideo.setChecked(true);
        rgMode.setOnCheckedChangeListener((g, id) -> updateForKind());
        LinearLayout modeCard = card();
        modeCard.addView(rgMode);
        root.addView(modeCard);

        // ---- 图片设置 ----
        boxImage = card();
        boxImage.addView(label("输出图片格式"));
        spImageTarget = new Spinner(this);
        boxImage.addView(spImageTarget);
        boxImage.addView(label("压缩质量"));
        sbQuality = new SeekBar(this);
        sbQuality.setMax(100);
        sbQuality.setProgress(90);
        tvQualityLabel = new TextView(this);
        tvQualityLabel.setTextSize(12);
        tvQualityLabel.setTextColor(Color.parseColor("#6B7280"));
        sbQuality.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar sb, int p, boolean fromUser) {
                tvQualityLabel.setText("质量 " + Math.max(1, p) + "%（仅对 JPEG / WebP 生效）");
            }

            public void onStartTrackingTouch(SeekBar sb) {
            }

            public void onStopTrackingTouch(SeekBar sb) {
            }
        });
        tvQualityLabel.setText("质量 90%（仅对 JPEG / WebP 生效）");
        boxImage.addView(sbQuality);
        boxImage.addView(tvQualityLabel);
        boxImage.addView(label("长边限制"));
        spImageEdge = new Spinner(this);
        boxImage.addView(spImageEdge);
        root.addView(boxImage);

        // ---- 视频设置 ----
        boxVideo = card();
        boxVideo.addView(label("输出格式（只列出本机支持的类型）"));
        spVideoTarget = new Spinner(this);
        boxVideo.addView(spVideoTarget);

        TextView capHint = new TextView(this);
        capHint.setText("本机可用：" + VideoConverter.capabilitySummary());
        capHint.setTextSize(11);
        capHint.setTextColor(Color.parseColor("#9CA3AF"));
        capHint.setPadding(0, dp(4), 0, 0);
        boxVideo.addView(capHint);

        boxVideo.addView(label("分辨率"));
        spVideoScale = new Spinner(this);
        boxVideo.addView(spVideoScale);
        boxVideo.addView(label("画质"));
        spVideoQuality = new Spinner(this);
        boxVideo.addView(spVideoQuality);
        cbKeepAudio = new CheckBox(this);
        cbKeepAudio.setText("保留音频");
        cbKeepAudio.setChecked(true);
        boxVideo.addView(cbKeepAudio);
        root.addView(boxVideo);

        populateSpinners();

        // 操作按钮
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        btnConvert = new Button(this);
        btnConvert.setText("开始转换");
        btnConvert.setAllCaps(false);
        btnConvert.setOnClickListener(v -> startConvert());
        btnOpen = new Button(this);
        btnOpen.setText("查看结果");
        btnOpen.setAllCaps(false);
        btnOpen.setEnabled(false);
        btnOpen.setOnClickListener(v -> openResult());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        actions.addView(btnConvert, lp);
        actions.addView(btnOpen, lp);
        root.addView(actions);

        tvStatus = new TextView(this);
        tvStatus.setTextSize(12);
        tvStatus.setTextColor(Color.parseColor("#374151"));
        tvStatus.setPadding(0, dp(10), 0, 0);
        root.addView(tvStatus);

        // 页脚：开发者与版本号
        TextView footer = new TextView(this);
        footer.setText("开发者：" + APP_AUTHOR + "　·　版本 " + APP_VERSION);
        footer.setTextSize(11);
        footer.setTextColor(Color.parseColor("#9CA3AF"));
        footer.setGravity(android.view.Gravity.CENTER);
        footer.setPadding(0, dp(16), 0, dp(4));
        root.addView(footer);

        TextView copyright = new TextView(this);
        copyright.setText("Copyright (C) 2026 " + APP_AUTHOR);
        copyright.setTextSize(10);
        copyright.setTextColor(Color.parseColor("#C0C4CC"));
        copyright.setGravity(android.view.Gravity.CENTER);
        copyright.setPadding(0, 0, 0, dp(8));
        root.addView(copyright);

        // 详细的格式说明放进「说明」弹窗，主界面保持精简
        this.scrollView = scroll;

        return scroll;
    }

    /** 使用说明弹窗（原本是一大段文字挂在界面底部，现在收起来）。 */
    private void showHelp() {
        TextView tv = new TextView(this);
        tv.setTextSize(13);
        tv.setPadding(dp(20), dp(16), dp(20), dp(8));
        tv.setMovementMethod(new android.text.method.ScrollingMovementMethod());
        tv.setText(
                "图片\n"
                        + "  可读：HEIC / JPEG / PNG / WebP / GIF / BMP / TIFF / AVIF 等\n"
                        + "  输出：JPEG / PNG / WebP（含无损）\n"
                        + "  可选压缩质量（仅 JPEG / WebP 生效）与长边限制\n\n"
                        + "视频\n"
                        + "  转码使用手机硬件编解码器，速度快、发热低\n"
                        + "  输出格式取决于本机支持的编码器，下拉里只列出可用的\n"
                        + "  可选分辨率与画质档位\n\n"
                        + "音频\n"
                        + "  可选择「只要音频」直接把视频里的音轨提取出来\n\n"
                        + "文件位置\n"
                        + "  结果保存在相册的 Movies / Pictures / Music 下的\n"
                        + "  MediaConv 文件夹，原文件不会被修改\n\n"
                        + "隐私\n"
                        + "  全程在本机完成，不联网、不上传任何文件\n\n"
                        + "开发者：" + APP_AUTHOR + "\n"
                        + "版本：" + APP_VERSION
        );

        new android.app.AlertDialog.Builder(this)
                .setTitle("使用说明")
                .setView(tv)
                .setPositiveButton("知道了", null)
                .show();
    }

    private LinearLayout card() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int p = dp(14);
        box.setPadding(p, p, p, p);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.WHITE);
        bg.setCornerRadius(dp(12));
        box.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(12);
        box.setLayoutParams(lp);
        return box;
    }

    private TextView label(String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextSize(12);
        tv.setTextColor(Color.parseColor("#6B7280"));
        tv.setPadding(0, dp(10), 0, dp(2));
        return tv;
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }

    // ------------------------------------------------------------------ 选项

    private List<ImageConverter.Format> availableImageFormats() {
        List<ImageConverter.Format> list = new ArrayList<>();
        for (ImageConverter.Format f : ImageConverter.Format.values()) {
            if (ImageConverter.isAvailable(f)) list.add(f);
        }
        return list;
    }

    private void populateSpinners() {
        // 图片格式
        List<String> imgLabels = new ArrayList<>();
        for (ImageConverter.Format f : imageTargets) {
            String label = f.ext.toUpperCase(Locale.US);
            if (f == ImageConverter.Format.WEBP_LOSSLESS) label = "WEBP 无损";
            imgLabels.add(label);
        }
        setAdapter(spImageTarget, imgLabels, 0);

        // 视频格式：直接用探测出来的可用列表
        List<String> vidLabels = new ArrayList<>();
        for (VideoConverter.Target t : videoTargets) vidLabels.add(t.label);
        int defaultIndex = videoTargets.indexOf(VideoConverter.Target.MP4_H264);
        setAdapter(spVideoTarget, vidLabels, Math.max(0, defaultIndex));

        // 分辨率
        List<String> scales = new ArrayList<>();
        for (VideoConverter.Scale s : VideoConverter.Scale.values()) scales.add(s.label);
        setAdapter(spVideoScale, scales, 0);

        // 画质
        List<String> qualities = new ArrayList<>();
        qualities.add("极小体积");
        qualities.add("小体积");
        qualities.add("均衡（推荐）");
        qualities.add("高画质");
        setAdapter(spVideoQuality, qualities, 2);

        // 图片长边限制
        List<String> edges = new ArrayList<>();
        edges.add("不限制（保持原尺寸）");
        edges.add("4096 px");
        edges.add("2560 px");
        edges.add("1920 px");
        edges.add("1280 px");
        edges.add("800 px");
        setAdapter(spImageEdge, edges, 0);
    }

    private void setAdapter(Spinner spinner, List<String> items, int selection) {
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_item, items);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        if (selection >= 0 && selection < items.size()) spinner.setSelection(selection);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && scrollView != null) {
            // 布局完成后打一行日志：content/viewport/scrollable
            // 如果这里显示 scrollable=true 但手指仍拖不动，问题就在触控层而不是布局
            scrollView.post(() -> scrollView.logMetrics("windowFocused"));
        }
    }

    private void updateForKind() {
        boolean image = rbImage.isChecked();
        boxImage.setVisibility(image ? View.VISIBLE : View.GONE);
        boxVideo.setVisibility(image ? View.GONE : View.VISIBLE);
        if (scrollView != null) {
            scrollView.post(() -> {
                scrollView.logMetrics("modeChanged");
                scrollView.scrollTo(0, 0);
            });
        }
    }

    // ------------------------------------------------------------------ 选择文件

    private void pickFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "image/*", "video/*", "audio/*", "application/octet-stream"
        });
        try {
            startActivityForResult(intent, REQ_PICK);
        } catch (Throwable t) {
            Toast.makeText(this, "无法打开文件选择器：" + t.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_PICK || resultCode != RESULT_OK || data == null) return;
        Uri uri = data.getData();
        if (uri == null) return;
        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Throwable ignored) {
        }
        srcUri = uri;
        srcName = queryName(uri);
        srcKind = kindOf(srcName);
        tvFile.setText(srcName);
        if (srcKind == Kind.IMAGE) {
            rbImage.setChecked(true);
        } else if (srcKind == Kind.VIDEO || srcKind == Kind.AUDIO) {
            rbVideo.setChecked(true);
        }
        updateForKind();
        probeInfo();
        btnOpen.setEnabled(false);
        tvStatus.setText("");
    }

    private void probeInfo() {
        final Uri uri = srcUri;
        final Kind kind = srcKind;
        if (uri == null) return;
        tvInfo.setText("读取中…");
        pool.execute(() -> {
            String info = kind == Kind.IMAGE ? "图片文件" : VideoConverter.describe(MainActivity.this, uri);
            ui.post(() -> tvInfo.setText(info == null || info.isEmpty() ? "—" : info));
        });
    }

    private String queryName(Uri uri) {
        String name = null;
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) name = c.getString(idx);
            }
        } catch (Throwable ignored) {
        }
        if (name == null) {
            String path = uri.getLastPathSegment();
            name = path == null ? "input" : path.substring(path.lastIndexOf('/') + 1);
        }
        return name;
    }

    private static Kind kindOf(String name) {
        String lower = name.toLowerCase(Locale.US);
        int dot = lower.lastIndexOf('.');
        if (dot < 0) return Kind.UNKNOWN;
        String ext = lower.substring(dot);
        for (String e : IMAGE_EXTS) if (e.equals(ext)) return Kind.IMAGE;
        for (String e : VIDEO_EXTS) if (e.equals(ext)) return Kind.VIDEO;
        for (String e : AUDIO_EXTS) if (e.equals(ext)) return Kind.AUDIO;
        return Kind.UNKNOWN;
    }

    // ------------------------------------------------------------------ 转换

    private void startConvert() {
        if (srcUri == null) {
            Toast.makeText(this, "请先选择要转换的文件", Toast.LENGTH_SHORT).show();
            return;
        }
        boolean image = rbImage.isChecked();
        if (!image && srcKind == Kind.IMAGE) {
            Toast.makeText(this, "这是图片文件，请切换到「图片转换」", Toast.LENGTH_LONG).show();
            return;
        }
        if (image && (srcKind == Kind.VIDEO || srcKind == Kind.AUDIO)) {
            Toast.makeText(this, "这是视频/音频文件，请切换到「视频/音频转换」", Toast.LENGTH_LONG).show();
            return;
        }
        if (image) doImage(); else doVideo();
    }

    private void doImage() {
        final ImageConverter.Format fmt = imageFormatAt(spImageTarget.getSelectedItemPosition());
        final int quality = Math.max(1, sbQuality.getProgress());
        final int maxEdge = edgeAt(spImageEdge.getSelectedItemPosition());

        final ProgressDialog dlg = progressDialog("正在转换图片…");
        dlg.show();
        cancelled = false;

        pool.execute(() -> {
            Uri out = null;
            String err = null;
            try {
                out = createOutput(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, fmt.mime, fmt.ext);
                ImageConverter.convert(MainActivity.this, srcUri, out, fmt, quality, maxEdge,
                        true, msg -> ui.post(() -> dlg.setMessage(msg)));
                // Android 10+ 写入时标记为 pending，完成后必须清除，否则相册里看不到
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues done = new ContentValues();
                    done.put(MediaStore.MediaColumns.IS_PENDING, 0);
                    getContentResolver().update(out, done, null, null);
                }
            } catch (Throwable t) {
                err = t.getMessage() == null ? t.toString() : t.getMessage();
            }
            final Uri fOut = out;
            final String fErr = err;
            ui.post(() -> {
                dlg.dismiss();
                if (fErr != null) {
                    tvStatus.setText("失败：" + fErr);
                    if (fOut != null) getContentResolver().delete(fOut, null, null);
                    Toast.makeText(this, "转换失败：" + fErr, Toast.LENGTH_LONG).show();
                } else {
                    lastOutput = fOut;
                    btnOpen.setEnabled(true);
                    tvStatus.setText("已保存：" + describeOutput(fOut));
                    Toast.makeText(this, "转换完成", Toast.LENGTH_SHORT).show();
                }
            });
        });
    }

    private void doVideo() {
        final VideoConverter.Target target = targetAt(spVideoTarget.getSelectedItemPosition());
        final VideoConverter.Options opt = new VideoConverter.Options();
        opt.target = target;
        opt.scale = scaleAt(spVideoScale.getSelectedItemPosition());
        opt.includeAudio = cbKeepAudio.isChecked();
        int q = spVideoQuality.getSelectedItemPosition();
        opt.crfLikeQuality = new int[]{34, 28, 23, 19}[Math.max(0, Math.min(3, q))];

        final ProgressDialog dlg = progressDialog("正在转码…（大文件需要一些时间）");
        dlg.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        dlg.setMax(100);
        dlg.show();
        cancelled = false;

        pool.execute(() -> {
            Uri out = null;
            String err = null;
            VideoConverter.Result result = null;
            java.io.File tmpFile = null;
            try {
                // 先写应用私有临时文件：MediaMuxer 在 API 24 只支持文件路径，
                // 用临时文件既兼容老系统，也避免中途失败留下半个媒体文件。
                tmpFile = new java.io.File(getCacheDir(),
                        "transcode_" + System.currentTimeMillis() + "." + target.ext);
                result = VideoConverter.convert(MainActivity.this, srcUri, tmpFile.getAbsolutePath(), opt,
                        new VideoConverter.Callback() {
                            public void onProgress(double fraction, String stage, String detail) {
                                ui.post(() -> {
                                    if (fraction >= 0) dlg.setProgress((int) (fraction * 100));
                                    dlg.setMessage(stage + (detail.isEmpty() ? "" : "\n" + detail));
                                });
                            }

                            public boolean isCancelled() {
                                return cancelled;
                            }
                        });

                if (result.ok && tmpFile.length() > 0) {
                    Uri collection = target.hasVideo
                            ? MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                            : MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
                    out = createOutput(collection, target.mime, target.ext);
                    try (InputStream in = new java.io.FileInputStream(tmpFile);
                         OutputStream os = getContentResolver().openOutputStream(out, "w")) {
                        if (os == null) throw new IOException("无法写入输出文件");
                        byte[] buf = new byte[256 * 1024];
                        int n;
                        while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
                        os.flush();
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        ContentValues done = new ContentValues();
                        done.put(MediaStore.MediaColumns.IS_PENDING, 0);
                        getContentResolver().update(out, done, null, null);
                    }
                } else {
                    err = (result.message == null || result.message.isEmpty())
                            ? "转换未产生有效输出" : result.message;
                }
            } catch (Throwable t) {
                err = t.getMessage() == null ? t.toString() : t.getMessage();
            } finally {
                if (tmpFile != null) tmpFile.delete();
            }
            final Uri fOut = out;
            final String fErr = err;
            final VideoConverter.Result fRes = result;
            ui.post(() -> {
                dlg.dismiss();
                if (fErr != null) {
                    tvStatus.setText("失败：" + fErr);
                    if (fOut != null) getContentResolver().delete(fOut, null, null);
                    Toast.makeText(this, "转换失败：" + fErr, Toast.LENGTH_LONG).show();
                } else {
                    lastOutput = fOut;
                    btnOpen.setEnabled(true);
                    StringBuilder sb = new StringBuilder("已保存：");
                    if (fRes.hasVideo) {
                        sb.append(fRes.outWidth).append("×").append(fRes.outHeight).append(" · ");
                    } else {
                        sb.append("音频 · ");
                    }
                    sb.append(String.format(Locale.US, "%.1f 秒", fRes.durationSec));
                    if (fRes.warning != null && !fRes.warning.isEmpty()) {
                        sb.append("\n注意：").append(fRes.warning);
                    }
                    tvStatus.setText(sb.toString());
                    Toast.makeText(this, "转换完成", Toast.LENGTH_SHORT).show();
                }
            });
        });
    }

    private ProgressDialog progressDialog(String msg) {
        ProgressDialog d = new ProgressDialog(this);
        d.setMessage(msg);
        d.setCancelable(false);
        d.setButton(ProgressDialog.BUTTON_NEGATIVE, "取消", (dialog, which) -> {
            cancelled = true;
            dialog.dismiss();
        });
        return d;
    }

    private Uri createOutput(Uri collection, String mime, String ext) throws IOException {
        String base = srcName;
        int dot = base.lastIndexOf('.');
        if (dot > 0) base = base.substring(0, dot);
        String name = base + "_converted_" + System.currentTimeMillis() + "." + ext;

        ContentValues cv = new ContentValues();
        cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
        cv.put(MediaStore.MediaColumns.MIME_TYPE, mime);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            String dir;
            if (MediaStore.Video.Media.EXTERNAL_CONTENT_URI.equals(collection)) {
                dir = Environment.DIRECTORY_MOVIES;
            } else if (MediaStore.Audio.Media.EXTERNAL_CONTENT_URI.equals(collection)) {
                dir = Environment.DIRECTORY_MUSIC;
            } else {
                dir = Environment.DIRECTORY_PICTURES;
            }
            cv.put(MediaStore.MediaColumns.RELATIVE_PATH, dir + "/MediaConv");
            cv.put(MediaStore.MediaColumns.IS_PENDING, 1);
        }
        Uri uri = getContentResolver().insert(collection, cv);
        if (uri == null) throw new IOException("无法创建输出文件（存储空间或权限不足）");
        return uri;
    }

    private String describeOutput(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) return c.getString(idx);
            }
        } catch (Throwable ignored) {
        }
        return uri.getLastPathSegment() == null ? "输出文件" : uri.getLastPathSegment();
    }

    private void openResult() {
        if (lastOutput == null) return;
        try {
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(lastOutput, getContentResolver().getType(lastOutput));
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(i);
        } catch (Throwable t) {
            Toast.makeText(this, "没有找到能打开该文件的应用", Toast.LENGTH_SHORT).show();
        }
    }

    // ------------------------------------------------------------------ 选项取值

    private ImageConverter.Format imageFormatAt(int pos) {
        if (pos < 0 || pos >= imageTargets.size()) return ImageConverter.Format.JPEG;
        return imageTargets.get(pos);
    }

    private VideoConverter.Target targetAt(int pos) {
        if (pos < 0 || pos >= videoTargets.size()) return VideoConverter.Target.MP4_H264;
        return videoTargets.get(pos);
    }

    private static int edgeAt(int pos) {
        int[] edges = {0, 4096, 2560, 1920, 1280, 800};
        if (pos < 0 || pos >= edges.length) return 0;
        return edges[pos];
    }

    private static VideoConverter.Scale scaleAt(int pos) {
        VideoConverter.Scale[] all = VideoConverter.Scale.values();
        if (pos < 0 || pos >= all.length) return VideoConverter.Scale.KEEP;
        return all[pos];
    }

    @Override
    protected void onDestroy() {
        cancelled = true;
        pool.shutdownNow();
        super.onDestroy();
    }
}
