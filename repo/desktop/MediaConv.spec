# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成免安装绿色版（onedir）。

设计取舍：
  * 用 onedir 而不是 onefile：onefile 每次启动都要把 500MB+ 解压到临时目录，
    启动要十几秒；onedir 启动是瞬间的，更适合这种带大体积 ffmpeg 的程序。
  * 只收集 QtCore/QtGui/QtWidgets 及其依赖，剔掉 QtWebEngine、Qt3D、Quick 等
    用不到的模块，能省下大量体积。
  * ffmpeg.exe / ffprobe.exe 直接放进 bin/，程序启动时自动查找。
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve()          # noqa: F821  (SPECPATH 由 PyInstaller 注入)
# 同一个 spec 需要同时适配两种目录布局：
#   开发布局   <工作区>/MediaConverter/MediaConv.spec  -> 桌面版源码在 <工作区>/MediaConverter/desktop/
#   仓库布局   <仓库>/desktop/MediaConv.spec            -> 桌面版源码就在本目录
# 靠"同目录下有没有 MediaConv.py"来判断，比写死路径更稳。
if (ROOT / "MediaConv.py").exists():
    DESKTOP = ROOT
    ROOT = ROOT.parent
else:
    DESKTOP = ROOT / "desktop"
BIN_DIR = DESKTOP / "bin"

# ---------------------------------------------------------------- 数据文件
datas = []
binaries = []

# ffmpeg / ffprobe 随程序分发
for exe in ("ffmpeg.exe", "ffprobe.exe"):
    p = BIN_DIR / exe
    if p.exists():
        binaries.append((str(p), "bin"))

# HEIC / AVIF 插件自带的原生库（libheif、libx265 等）
for pkg in ("pillow_heif", "pillow_avif"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
    except Exception as e:  # 插件没装就跳过
        print(f"[spec] 跳过 {pkg}: {e}")

# pillow_heif / pillow_avif 的扩展模块被放在 site-packages 根目录
PYLIBS = Path(__import__("PIL").__file__).resolve().parent.parent
for pattern in ("_pillow_heif*.pyd", "_pillow_heif*.so", "_avif*.pyd", "_avif*.so",
                "libheif*.dll", "libx265*.dll", "libstdc++*.dll", "libgcc*.dll",
                "libde265*.dll", "libaom*.dll"):
    for f in PYLIBS.glob(pattern):
        binaries.append((str(f), "."))

# ---------------------------------------------------------------- Qt 裁剪
excludes = [
    # 用不到的大块
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtUiTools", "PySide6.QtNetwork",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtLocation",
    "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtPrintSupport",
    # 其它用不到的科学计算/开发库
    "matplotlib", "scipy", "pandas", "IPython", "jupyter", "notebook",
    "pytest", "unittest", "pydoc", "doctest", "tkinter", "test",
    "numpy.f2py", "setuptools", "pip", "wheel",
]

a = Analysis(  # noqa: F821
    [str(DESKTOP / "MediaConv.py")],
    pathex=[str(DESKTOP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "mediaconv", "mediaconv.Cli", "mediaconv.Gui", "mediaconv.Jobs",
        "mediaconv.Formats", "mediaconv.Images", "mediaconv.Video", "mediaconv.FFmpeg",
        "PIL._tkinter_finder",
        "pillow_heif", "pillow_avif",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaConv",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=False => 生成 GUI 子系统可执行文件。
    # 这样双击或从快捷方式启动时，Windows 根本不会创建控制台窗口
    # （之前用 console=True，黑窗口会先闪出来，事后再隐藏已经晚了）。
    # 命令行模式由 MediaConv.py 里的 _attach_parent_console() 主动接上父进程控制台。
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    version=str(ROOT / "tools" / "version_info.txt") if (ROOT / "tools" / "version_info.txt").exists() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MediaConv",
)
