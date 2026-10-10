"""图形界面（PySide6）。

结构：
    顶部工具栏  —— 添加文件/文件夹、清空、开始/停止
    中间左：文件列表（支持拖拽）
    中间右：格式设置（图片 / 视频 两组，按队列内容自动切换）
    底部：总进度条 + 状态文本
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import FFmpeg, Formats, Images, Video
from .Jobs import ConvertSettings, Job, JobRunner, Kind, State

APP_TITLE = "格式转换器 MediaConv"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "xiaoke"
COLOR_OK = QColor("#1a7f37")
COLOR_FAIL = QColor("#c0392b")
COLOR_RUN = QColor("#0b6bcb")
COLOR_SKIP = QColor("#8a6d3b")

IMAGE_EXT_FILTER = " ".join(f"*{e}" for e in sorted(Formats.IMAGE_EXTS))
VIDEO_EXT_FILTER = " ".join(f"*{e}" for e in sorted(Formats.VIDEO_EXTS | Formats.AUDIO_EXTS))


# --------------------------------------------------------------------------------------
# 后台线程 -> Qt 信号桥
# --------------------------------------------------------------------------------------


class WorkerBridge(QObject):
    """把 JobRunner 的回调转成 Qt 信号（跨线程安全）。"""

    jobChanged = Signal(object)
    finished = Signal(object)
    logLine = Signal(object, str)


class ConvertWorker(QThread):
    """在独立线程里跑 JobRunner，避免阻塞界面。"""

    def __init__(self, runner: JobRunner, settings: ConvertSettings, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.settings = settings

    def run(self) -> None:  # 在子线程执行
        self.runner.start(self.settings)


# --------------------------------------------------------------------------------------
# 主窗口
# --------------------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1120, 720)
        self.setAcceptDrops(True)

        self.runner = JobRunner()
        self.bridge = WorkerBridge()
        self.runner.on_job_update = self.bridge.jobChanged.emit
        self.runner.on_finished = self.bridge.finished.emit
        self.runner.on_log = lambda job, line: self.bridge.logLine.emit(job, line)
        self.bridge.jobChanged.connect(self._on_job_changed)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.logLine.connect(self._on_log_line)

        self.worker: ConvertWorker | None = None
        self._row_of: dict[int, int] = {}   # id(job) -> 表格行号

        self._build_ui()
        self._refresh_format_lists()
        self._check_environment()

    # ------------------------------------------------------------------ 界面搭建
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        root.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_file_panel())
        splitter.addWidget(self._build_settings_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([680, 420])
        root.addWidget(splitter, 1)

        root.addLayout(self._build_progress_bar())
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self):
        bar = QHBoxLayout()
        bar.setSpacing(6)

        def mk(text: str, slot, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            b.setMinimumHeight(30)
            return b

        self.btn_add_files = mk("添加文件", self.add_files, "选择要转换的图片/视频/音频（可多选）")
        self.btn_add_dir = mk("添加文件夹", self.add_folder, "把整个文件夹里的媒体文件加入队列")
        self.btn_remove = mk("移除选中", self.remove_selected, "从队列中移除选中的文件")
        self.btn_clear = mk("清空列表", self.clear_list, "清空整个队列")
        self.btn_open_out = mk("打开输出目录", self.open_output_dir, "在资源管理器中打开输出文件夹")
        self.btn_about = mk("关于", self.show_about, "版本与发行信息")

        bar.addWidget(self.btn_add_files)
        bar.addWidget(self.btn_add_dir)
        bar.addWidget(self.btn_remove)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        bar.addWidget(self.btn_open_out)
        bar.addWidget(self.btn_about)
        return bar

    def show_about(self) -> None:
        caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
        st = Images.plugin_status()
        ff_ver = caps.version or "未找到"
        text = (
            f"<h3>{APP_TITLE}</h3>"
            "<p style='margin:0'>"
            f"<b>版本号：{APP_VERSION}</b><br>"
            f"发行者：<b>{APP_PUBLISHER}</b>"
            "</p>"
            "<p>图片 / 视频 / 音频 格式转换工具，全部在本机完成，不联网、不上传文件。</p>"
            "<hr>"
            f"<p><b>运行环境</b><br>"
            f"FFmpeg：{ff_ver}<br>"
            f"HEIC 支持：{'是' if st.get('heif') else '否'}　"
            f"AVIF 支持：{'是' if st.get('avif') else '否'}<br>"
            f"可输出：图片 {len(self._image_targets)} 种 / 视频音频 {len(self._video_targets)} 种</p>"
            "<hr>"
            f"<p style='color:#666'>发行者：{APP_PUBLISHER}　版本：{APP_VERSION}<br>"
            "本程序内置 FFmpeg（GPL 许可），遵循其开源许可协议分发。<br>"
            "Python / PySide6 / Pillow 等组件版权归各自作者所有。</p>"
        )
        box = QMessageBox(self)
        box.setWindowTitle("关于")
        box.setTextFormat(Qt.RichText)
        box.setText(text)
        box.setIconPixmap(_make_window_icon().pixmap(64, 64))
        box.exec()

    def _build_file_panel(self) -> QWidget:
        box = QGroupBox("待转换文件")
        lay = QVBoxLayout(box)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件名", "类型", "状态", "进度", "结果"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i, w in ((1, 64), (2, 74), (3, 64), (4, 150)):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, w)
        lay.addWidget(self.table)

        self.lbl_drop = QLabel("把文件或文件夹拖到这里也可以 →")
        self.lbl_drop.setStyleSheet("color:#888; padding:2px;")
        lay.addWidget(self.lbl_drop)
        return box

    def _build_settings_panel(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_video_tab(), "视频 / 音频")
        self.tabs.addTab(self._build_image_tab(), "图片")
        self.tabs.addTab(self._build_output_tab(), "输出")
        lay.addWidget(self.tabs)

        self.btn_start = QPushButton("开始转换")
        self.btn_start.setMinimumHeight(40)
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.btn_start.setFont(f)
        self.btn_start.clicked.connect(self.start_convert)
        lay.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("停止")
        self.btn_cancel.setMinimumHeight(30)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_convert)
        lay.addWidget(self.btn_cancel)
        return outer

    def _build_video_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.cmb_video_fmt = QComboBox()
        self.cmb_video_fmt.currentIndexChanged.connect(self._on_video_fmt_changed)
        form.addRow("目标格式", self.cmb_video_fmt)

        self.cmb_preset = QComboBox()
        for label, key in (("高画质（体积大）", "high"), ("均衡（推荐）", "balanced"),
                           ("小体积", "small"), ("极小体积", "tiny")):
            self.cmb_preset.addItem(label, key)
        self.cmb_preset.setCurrentIndex(1)
        form.addRow("画质", self.cmb_preset)

        self.cmb_scale = QComboBox()
        for label, key in (("保持原始分辨率", "keep"), ("4K 2160p", "2160"), ("2K 1440p", "1440"),
                           ("1080p", "1080"), ("720p", "720"), ("480p", "480"), ("360p", "360")):
            self.cmb_scale.addItem(label, key)
        form.addRow("分辨率", self.cmb_scale)

        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(0, 120)
        self.spin_fps.setSpecialValueText("保持原始帧率")
        self.spin_fps.setSuffix(" fps")
        form.addRow("帧率", self.spin_fps)

        self.cmb_audio = QComboBox()
        for label, key in (("重新编码（推荐）", "encode"), ("直接复制（快）", "keep"), ("不要音频", "none")):
            self.cmb_audio.addItem(label, key)
        form.addRow("音频", self.cmb_audio)

        self.cmb_abitrate = QComboBox()
        for b in ("96k", "128k", "192k", "256k", "320k"):
            self.cmb_abitrate.addItem(b, b)
        self.cmb_abitrate.setCurrentText("192k")
        form.addRow("音频码率", self.cmb_abitrate)

        self.chk_copy = QCheckBox("仅换容器（不重新编码，极快）")
        self.chk_copy.setToolTip("只把内容换个外壳，画质零损失、速度极快；\n但要求原编码能被目标容器接受，否则会失败。")
        form.addRow("", self.chk_copy)
        return w

    def _build_image_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.cmb_image_fmt = QComboBox()
        form.addRow("目标格式", self.cmb_image_fmt)

        self.spin_quality = QSpinBox()
        self.spin_quality.setRange(1, 100)
        self.spin_quality.setValue(90)
        form.addRow("质量", self.spin_quality)

        self.cmb_resize = QComboBox()
        for label, key in (("不缩放", "none"), ("按百分比", "percent"), ("指定宽度", "width"),
                           ("指定高度", "height"), ("限制最长边", "max")):
            self.cmb_resize.addItem(label, key)
        self.cmb_resize.currentIndexChanged.connect(self._on_resize_changed)
        form.addRow("缩放", self.cmb_resize)

        self.spin_resize = QSpinBox()
        self.spin_resize.setRange(0, 20000)
        self.spin_resize.setValue(100)
        self.spin_resize.setEnabled(False)
        form.addRow("数值", self.spin_resize)

        self.edit_bg = QLineEdit("#FFFFFF")
        self.edit_bg.setToolTip("带透明的图片转成 JPEG/BMP 等不支持透明的格式时，透明区域填充的颜色。")
        form.addRow("背景色", self.edit_bg)

        self.chk_meta = QCheckBox("保留 EXIF 等元数据")
        form.addRow("", self.chk_meta)

        hint = QLabel(
            "提示：转换后的常见选择——\n"
            "  发微信/网页用 WebP 或 JPEG\n"
            "  iPhone 照片想变小用 HEIC\n"
            "  要无损归档用 PNG / TIFF"
        )
        hint.setStyleSheet("color:#666; padding-top:6px;")
        hint.setWordWrap(True)
        form.addRow(hint)
        return w

    def _build_output_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        row = QHBoxLayout()
        self.edit_outdir = QLineEdit()
        self.edit_outdir.setPlaceholderText("留空 = 输出到原文件所在文件夹")
        btn = QPushButton("浏览…")
        btn.clicked.connect(self.pick_outdir)
        row.addWidget(self.edit_outdir, 1)
        row.addWidget(btn)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("输出位置", holder)

        self.edit_suffix = QLineEdit("_converted")
        form.addRow("文件名后缀", self.edit_suffix)

        self.chk_overwrite = QCheckBox("允许覆盖同名文件")
        form.addRow("", self.chk_overwrite)

        info = QLabel(
            "默认不会覆盖任何已有文件：\n"
            "同名时自动加 _1、_2 后缀。"
        )
        info.setStyleSheet("color:#666; padding-top:6px;")
        info.setWordWrap(True)
        form.addRow(info)
        return w

    def _build_progress_bar(self):
        box = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setMinimumWidth(260)
        box.addWidget(self.progress, 1)
        box.addWidget(self.lbl_status)
        return box

    # ------------------------------------------------------------------ 格式下拉
    def _refresh_format_lists(self) -> None:
        caps = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()) if FFmpeg.ffmpeg_path() else Formats.FFmpegCaps()
        self._video_targets = Formats.available_video_targets(caps)

        self.cmb_video_fmt.blockSignals(True)
        self.cmb_video_fmt.clear()
        for t in self._video_targets:
            label = f"{t.label}    → {t.ext}"
            self.cmb_video_fmt.addItem(label, t.key)
        self.cmb_video_fmt.blockSignals(False)

        self._image_targets = Formats.available_image_formats()
        self.cmb_image_fmt.clear()
        for f in self._image_targets:
            tags = []
            if f.supports_alpha:
                tags.append("透明")
            if f.supports_multi:
                tags.append("动图")
            suffix = f"    [{ '/'.join(tags) }]" if tags else ""
            self.cmb_image_fmt.addItem(f"{f.label}{suffix}", f.key)

    def _on_video_fmt_changed(self) -> None:
        key = self.cmb_video_fmt.currentData()
        t = next((x for x in self._video_targets if x.key == key), None)
        if t is None:
            return
        # 音频格式时禁用无关选项
        is_audio = t.kind == "audio"
        for widget in (self.cmb_scale, self.spin_fps, self.chk_copy):
            widget.setEnabled(not is_audio)
        if t.key == "gif_anim" and self.spin_fps.value() == 0:
            self.spin_fps.setValue(12)
        if t.notes:
            self.cmb_video_fmt.setToolTip(t.notes)

    def _on_resize_changed(self) -> None:
        mode = self.cmb_resize.currentData()
        self.spin_resize.setEnabled(mode != "none")
        if mode == "percent":
            self.spin_resize.setRange(1, 2000)
            self.spin_resize.setValue(100)
            self.spin_resize.setSuffix(" %")
        elif mode in ("width", "height", "max"):
            self.spin_resize.setRange(16, 20000)
            self.spin_resize.setValue(1920 if mode != "max" else 2000)
            self.spin_resize.setSuffix(" px")
        else:
            self.spin_resize.setSuffix("")

    # ------------------------------------------------------------------ 环境检查
    def _check_environment(self) -> None:
        problems = []
        if FFmpeg.ffmpeg_path() is None:
            problems.append("未找到 ffmpeg，视频/音频转换不可用（请把 ffmpeg.exe 放到程序目录的 bin 文件夹）")
        st = Images.plugin_status()
        if not st.get("heif"):
            problems.append("未加载 HEIC 插件，iPhone 的 .heic 照片无法转换")
        if problems:
            self.statusBar().showMessage("⚠ " + "；".join(problems))
            self.lbl_status.setText("环境不完整，详见下方提示")
            self.lbl_status.setStyleSheet("color:#c0392b;")
        else:
            n_img = len(self._image_targets)
            n_vid = len(self._video_targets)
            ff_ver = Formats.probe_ffmpeg(FFmpeg.ffmpeg_path()).version
            self.statusBar().showMessage(
                f"就绪 · 版本 {APP_VERSION} · 发行者 {APP_PUBLISHER} · "
                f"图片 {n_img} 种 / 视频音频 {n_vid} 种输出格式 · ffmpeg {ff_ver}"
            )

    # ------------------------------------------------------------------ 文件增删
    def add_files(self) -> None:
        exts = f"媒体文件 ({IMAGE_EXT_FILTER} {VIDEO_EXT_FILTER});;所有文件 (*.*)"
        files, _ = QFileDialog.getOpenFileNames(self, "选择要转换的文件", "", exts)
        if files:
            self._add_paths(files)

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件夹（会扫描其中的媒体文件）")
        if d:
            self._add_paths([d])

    def _add_paths(self, paths: list[str]) -> None:
        expanded: list[Path] = []
        for p in paths:
            path = Path(p)
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and child.suffix.lower() in (
                        Formats.IMAGE_EXTS | Formats.VIDEO_EXTS | Formats.AUDIO_EXTS
                    ):
                        expanded.append(child)
            elif path.is_file():
                expanded.append(path)

        added = self.runner.add(expanded)
        for job in added:
            self._append_row(job)
        if added:
            self._auto_select_output(jobs=added)
            self.lbl_status.setText(f"已加入 {len(added)} 个文件，共 {len(self.runner.jobs)} 个")

    def _append_row(self, job: Job) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_of[id(job)] = row
        kind_text = {Kind.IMAGE: "图片", Kind.VIDEO: "视频", Kind.AUDIO: "音频"}.get(job.kind, "未知")
        items = [
            QTableWidgetItem(job.name),
            QTableWidgetItem(kind_text),
            QTableWidgetItem("等待"),
            QTableWidgetItem("0%"),
            QTableWidgetItem(""),
        ]
        items[0].setToolTip(str(job.src))
        for col, it in enumerate(items):
            self.table.setItem(row, col, it)

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        jobs_to_remove = []
        for r in rows:
            name_item = self.table.item(r, 0)
            for job in self.runner.jobs:
                if job.name == name_item.text() and id(job) in self._row_of and self._row_of[id(job)] == r:
                    jobs_to_remove.append(job)
                    break
            self.table.removeRow(r)
        self.runner.remove(jobs_to_remove)
        self._rebuild_row_index()
        self.lbl_status.setText(f"队列剩余 {len(self.runner.jobs)} 个文件")

    def clear_list(self) -> None:
        if self.runner.running:
            QMessageBox.information(self, "提示", "正在转换中，请先停止再清空。")
            return
        self.runner.jobs.clear()
        self.table.setRowCount(0)
        self._row_of.clear()
        self.progress.setValue(0)
        self.lbl_status.setText("已清空")

    def _rebuild_row_index(self) -> None:
        self._row_of.clear()
        for r in range(self.table.rowCount()):
            for job in self.runner.jobs:
                if job.name == self.table.item(r, 0).text():
                    self._row_of[id(job)] = r
                    break

    def _auto_select_output(self, jobs: list[Job]) -> None:
        """根据队列内容自动切到合适的选项卡。"""
        kinds = {j.kind for j in jobs}
        if kinds == {Kind.IMAGE}:
            self.tabs.setCurrentIndex(1)
        elif kinds - {Kind.IMAGE}:
            self.tabs.setCurrentIndex(0)

    def pick_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if d:
            self.edit_outdir.setText(d)

    def open_output_dir(self) -> None:
        d = self.edit_outdir.text().strip()
        target = Path(d) if d else None
        if target is None:
            for job in self.runner.jobs:
                if job.output:
                    target = job.output.parent
                    break
        if target is None or not target.exists():
            QMessageBox.information(self, "提示", "还没有输出目录。转换完成后这里会自动可用。")
            return
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", str(target)])

    # ------------------------------------------------------------------ 转换
    def _build_settings(self) -> ConvertSettings:
        s = ConvertSettings()
        s.out_dir = Path(self.edit_outdir.text().strip()) if self.edit_outdir.text().strip() else None
        s.overwrite = self.chk_overwrite.isChecked()
        s.suffix = self.edit_suffix.text()

        s.image.target_key = self.cmb_image_fmt.currentData() or "JPEG"
        s.image.quality = self.spin_quality.value()
        s.image.keep_metadata = self.chk_meta.isChecked()
        s.image.resize_mode = self.cmb_resize.currentData() or "none"
        s.image.resize_value = float(self.spin_resize.value())
        s.image.background = self.edit_bg.text() or "#FFFFFF"

        s.video.target_key = self.cmb_video_fmt.currentData() or "mp4_h264"
        s.video.quality = self.cmb_preset.currentData() or "balanced"
        s.video.scale = self.cmb_scale.currentData() or "keep"
        s.video.fps = float(self.spin_fps.value())
        s.video.audio_mode = self.cmb_audio.currentData() or "encode"
        s.video.audio_bitrate = self.cmb_abitrate.currentData() or "192k"
        s.video.copy_streams = self.chk_copy.isChecked()
        return s

    def start_convert(self) -> None:
        if self.runner.running:
            return
        if not self.runner.jobs:
            QMessageBox.information(self, "提示", "请先添加要转换的文件。")
            return
        if FFmpeg.ffmpeg_path() is None and any(j.kind != Kind.IMAGE for j in self.runner.jobs):
            QMessageBox.warning(self, "缺少 ffmpeg",
                                "队列中有视频/音频文件，但没有找到 ffmpeg。\n"
                                "请把 ffmpeg.exe / ffprobe.exe 放到程序目录的 bin 文件夹后重试。")
            return

        # 重置状态
        for job in self.runner.jobs:
            if job.state in (State.DONE, State.FAILED, State.CANCELLED, State.SKIPPED):
                job.state = State.PENDING
                job.progress = 0.0
                job.error = ""
                job.message = ""
                job.out_size = 0
                self._update_row(job)

        settings = self._build_settings()
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.lbl_status.setStyleSheet("")

        self.worker = ConvertWorker(self.runner, settings, self)
        self.worker.start()

    def cancel_convert(self) -> None:
        if self.runner.running:
            self.runner.cancel()
            self.lbl_status.setText("正在停止…（当前文件转换完即中止）")
            self.btn_cancel.setEnabled(False)

    @Slot(object)
    def _on_job_changed(self, job: Job) -> None:
        self._update_row(job)
        done = sum(1 for j in self.runner.jobs if j.state in (State.DONE, State.FAILED, State.SKIPPED, State.CANCELLED))
        total = len(self.runner.jobs)
        # 总进度 = 已完成文件比例 + 当前文件进度
        running = [j for j in self.runner.jobs if j.state == State.RUNNING]
        frac = (done + (running[0].progress if running else 0)) / max(1, total)
        self.progress.setValue(int(frac * 100))
        if running:
            j = running[0]
            self.lbl_status.setText(f"正在转换：{j.name}   {int(j.progress*100)}%  {j.speed}")
        else:
            self.lbl_status.setText(f"已完成 {done}/{total}")

    def _update_row(self, job: Job) -> None:
        row = self._row_of.get(id(job))
        if row is None or row >= self.table.rowCount():
            return
        state_text = {
            State.PENDING: "等待", State.RUNNING: "转换中", State.DONE: "完成",
            State.FAILED: "失败", State.CANCELLED: "已取消", State.SKIPPED: "跳过",
        }[job.state]
        color = {
            State.DONE: COLOR_OK, State.FAILED: COLOR_FAIL,
            State.RUNNING: COLOR_RUN, State.CANCELLED: COLOR_SKIP,
        }.get(job.state)

        it_state = self.table.item(row, 2)
        it_state.setText(state_text)
        it_state.setForeground(color or QColor("#000"))
        if job.state == State.FAILED and job.error:
            it_state.setToolTip(job.error)

        self.table.item(row, 3).setText(f"{int(job.progress*100)}%")

        if job.state == State.DONE and job.output:
            txt = job.output.name
            if job.ratio_text:
                txt += f"  {job.ratio_text}"
            if job.message:
                txt += f"  ({job.message})"
            it_res = self.table.item(row, 4)
            it_res.setText(txt)
            it_res.setForeground(COLOR_OK)
            it_res.setToolTip(str(job.output))
        elif job.state == State.FAILED:
            it_res = self.table.item(row, 4)
            first_line = (job.error or "").splitlines()
            it_res.setText(first_line[1] if len(first_line) > 1 else (job.error or "失败")[:60])
            it_res.setForeground(COLOR_FAIL)
            it_res.setToolTip(job.error)

    @Slot(object)
    def _on_finished(self, jobs: list[Job]) -> None:
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        oks = [j for j in jobs if j.state == State.DONE]
        fails = [j for j in jobs if j.state == State.FAILED]
        self.progress.setValue(100 if not fails else self.progress.value())
        msg = f"转换结束：成功 {len(oks)} 个"
        if fails:
            msg += f"，失败 {len(fails)} 个"
        self.lbl_status.setText(msg)
        self.statusBar().showMessage(msg)
        if fails:
            detail = "\n\n".join(f"• {j.name}\n  {j.error}" for j in fails[:6])
            more = f"\n\n… 还有 {len(fails)-6} 个失败" if len(fails) > 6 else ""
            QMessageBox.warning(self, "部分文件转换失败", detail + more)

    @Slot(object, str)
    def _on_log_line(self, job: Job, line: str) -> None:
        # 目前只保留最近一条在状态栏，避免界面卡顿
        if "error" in line.lower() or "Error" in line:
            self.statusBar().showMessage(line[:160])

    # ------------------------------------------------------------------ 拖拽支持
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.runner.running:
            ret = QMessageBox.question(self, "正在转换", "还有文件在转换，确定要退出吗？")
            if ret != QMessageBox.Yes:
                event.ignore()
                return
            self.runner.cancel()
        event.accept()


def _make_window_icon() -> QIcon:
    """用代码画一个简洁的图标，避免额外资源文件。"""
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#0b6bcb"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPointSize(26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "转")
    p.end()
    return QIcon(pm)


def run_gui(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(_make_window_icon())
    # 高 DPI 下的圆角/字体观感
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    win = MainWindow()
    win.show()
    return app.exec()
