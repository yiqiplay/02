"""转换任务队列：后台单线程执行，避免多任务抢占 CPU 导致每个都变慢。

GUI 与 CLI 共用本模块，保证两条入口行为一致。
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from . import FFmpeg, Formats, Images, Video


class Kind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UNKNOWN = "unknown"


class State(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class Job:
    """一个待转换的文件。"""

    src: Path
    kind: Kind = Kind.UNKNOWN
    state: State = State.PENDING
    progress: float = 0.0
    speed: str = ""
    output: Path | None = None
    message: str = ""
    error: str = ""
    in_size: int = 0
    out_size: int = 0
    elapsed: float = 0.0
    info: FFmpeg.MediaInfo | None = None
    log_tail: str = ""

    def __post_init__(self):
        self.src = Path(self.src)
        try:
            self.in_size = self.src.stat().st_size
        except OSError:
            self.in_size = 0

    @property
    def name(self) -> str:
        return self.src.name

    @property
    def ratio_text(self) -> str:
        if not self.in_size or not self.out_size:
            return ""
        return f"{(self.out_size - self.in_size) / self.in_size * 100:+.1f}%"


@dataclass
class ConvertSettings:
    """一套完整的转换设置，对队列中所有文件生效。"""

    image: Images.ImageOptions = field(default_factory=Images.ImageOptions)
    video: Video.VideoOptions = field(default_factory=Video.VideoOptions)
    out_dir: Path | None = None          # None 表示输出到源文件所在目录
    overwrite: bool = False
    suffix: str = "_converted"
    auto_kind_target: bool = True        # 图片文件自动用图片目标格式


def detect_kind(path: str | Path) -> Kind:
    """先按扩展名判断，扩展名不认识时用 ffprobe 兜底。"""
    p = Path(path)
    ext = p.suffix.lower()
    guess = Formats.classify_ext(ext)
    if guess == "image":
        # .gif 之类的动图仍算图片；但如果目标不是图片格式，后面会走视频通道
        return Kind.IMAGE
    if guess == "video":
        return Kind.VIDEO
    if guess == "audio":
        return Kind.AUDIO

    if FFmpeg.ffprobe_path() is not None:
        info = FFmpeg.probe(p)
        if info.has_video:
            return Kind.VIDEO
        if info.has_audio:
            return Kind.AUDIO
    return Kind.UNKNOWN


class JobRunner:
    """串行执行任务队列，通过回调把状态变化通知给界面。"""

    def __init__(
        self,
        on_job_update: Callable[[Job], None] | None = None,
        on_finished: Callable[[list[Job]], None] | None = None,
        on_log: Callable[[Job, str], None] | None = None,
    ):
        self.on_job_update = on_job_update or (lambda job: None)
        self.on_finished = on_finished or (lambda jobs: None)
        self.on_log = on_log or (lambda job, line: None)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.jobs: list[Job] = []
        self.settings = ConvertSettings()
        self._stop_after_current = False

    # ---------------------------------------------------------------- 队列管理
    def add(self, paths: list[str | Path]) -> list[Job]:
        added: list[Job] = []
        for p in paths:
            path = Path(p)
            if not path.exists() or not path.is_file():
                continue
            job = Job(src=path, kind=detect_kind(path))
            self.jobs.append(job)
            added.append(job)
        return added

    def remove(self, jobs: list[Job]) -> None:
        for j in jobs:
            if j in self.jobs:
                self.jobs.remove(j)

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if j.state in (State.PENDING, State.RUNNING)]

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    # ---------------------------------------------------------------- 执行
    def start(self, settings: ConvertSettings) -> bool:
        if self.running:
            return False
        self.settings = settings
        self._cancel.clear()
        self._stop_after_current = False
        self._thread = threading.Thread(target=self._run_all, name="mediaconv-worker", daemon=True)
        self._thread.start()
        return True

    def _run_all(self) -> None:
        try:
            for job in list(self.jobs):
                if self._cancel.is_set():
                    if job.state == State.PENDING:
                        job.state = State.CANCELLED
                        self.on_job_update(job)
                    continue
                if job.state in (State.DONE, State.SKIPPED):
                    continue
                self._run_one(job)
        finally:
            self.on_finished(list(self.jobs))

    def _run_one(self, job: Job) -> None:
        job.state = State.RUNNING
        job.progress = 0.0
        job.error = ""
        job.message = ""
        started = time.time()
        self.on_job_update(job)

        s = self.settings
        target_key = self._target_for(job)

        try:
            if job.kind == Kind.IMAGE:
                out = self._output_path(job, Images.output_extension(s.image.target_key), s)
                img_opt = s.image
                # 图片目标被"视频目标"覆盖时（比如要转成 GIF 动图），走 ffmpeg
                if target_key in _VIDEO_TARGET_KEYS:
                    self._run_video(job, out, s)
                else:
                    res = Images.convert_image(job.src, out, img_opt)
                    job.output = res.output
                    job.out_size = res.out_size
                    job.message = f"{res.width}×{res.height}" + ("" if res.frames <= 1 else f" · {res.frames}帧")
                    job.progress = 1.0
            else:
                out = self._output_path(job, Video._target(target_key).ext, s)
                self._run_video(job, out, s)

            job.state = State.DONE
            if not job.message:
                job.message = "完成"
        except FFmpeg.FFmpegNotFound as e:
            job.state = State.FAILED
            job.error = str(e)
        except (Images.ImageConvertError, Video.VideoConvertError) as e:
            job.state = State.FAILED
            job.error = str(e)
        except Exception as e:  # 兜底，避免一个坏文件把整个队列打断
            job.state = State.FAILED
            job.error = f"{type(e).__name__}: {e}"
            job.log_tail = traceback.format_exc()
        finally:
            job.elapsed = time.time() - started
            self.on_job_update(job)

    def _run_video(self, job: Job, out: Path, s: ConvertSettings) -> None:
        opt = s.video
        res = Video.convert_video(
            job.src,
            out,
            opt,
            on_progress=lambda frac, speed, t: self._progress(job, frac, speed),
            on_log=lambda line: self.on_log(job, line),
            cancel_check=self._cancel.is_set,
        )
        job.output = res.output
        job.out_size = res.out_size
        job.log_tail = res.log_tail
        job.progress = 1.0

    def _progress(self, job: Job, frac: float, speed: str) -> None:
        job.progress = frac
        job.speed = speed
        self.on_job_update(job)

    def _target_for(self, job: Job) -> str:
        s = self.settings
        if job.kind == Kind.IMAGE:
            return s.image.target_key
        return s.video.target_key

    def _output_path(self, job: Job, ext: str, s: ConvertSettings) -> Path:
        directory = Path(s.out_dir) if s.out_dir else job.src.parent
        directory.mkdir(parents=True, exist_ok=True)
        candidate = directory / f"{job.src.stem}{s.suffix}{ext}"
        if s.overwrite:
            return candidate
        n = 1
        while candidate.exists() and candidate.resolve() != job.src.resolve():
            candidate = directory / f"{job.src.stem}{s.suffix}_{n}{ext}"
            n += 1
        if candidate.resolve() == job.src.resolve():
            candidate = directory / f"{job.src.stem}{s.suffix}_out{ext}"
        return candidate


_VIDEO_TARGET_KEYS = {t.key for t in Formats.VIDEO_TARGETS}
