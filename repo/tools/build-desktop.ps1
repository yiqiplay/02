# Build the Windows portable (onedir) package.
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File tools\build-desktop.ps1 -Clean
#
# NOTE: keep this file pure ASCII -- Windows PowerShell 5.1 reads .ps1 as ANSI/GBK,
# so non-ASCII text here turns into mojibake and breaks parsing.
#
# Requirements:
#   1. Python 3.12 on PATH (or set $env:MEDIACONV_PYTHON to the interpreter)
#   2. PyInstaller:            python -m pip install pyinstaller
#   3. Runtime dependencies:   python -m pip install PySide6-Essentials pillow pillow-heif pillow-avif-plugin
#   4. FFmpeg binaries in desktop\bin\  (ffmpeg.exe + ffprobe.exe, see desktop\bin\README.md)

param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- locate paths
# Script lives in <repo>\tools\, so the repository root is one level up.
# This works both for a plain clone and for our dev layout (where the repo
# root is <workspace>\MediaConverter).
$repo = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $repo 'dist'

# ---------------------------------------------------------------- locate python
$py = $env:MEDIACONV_PYTHON
if (-not $py -or -not (Test-Path $py)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py -or -not (Test-Path $py)) {
    Write-Error "Python not found. Install Python 3.12 and put it on PATH, or set `$env:MEDIACONV_PYTHON."
    exit 2
}
Write-Host "[build] python : $py"

# Temporary/work dirs go under the repo so the build never writes outside it.
$tmp  = Join-Path $repo '.build-tmp'
$work = Join-Path $repo '.build-pyi'
New-Item -ItemType Directory -Force -Path $tmp, $work, $dist | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# ---------------------------------------------------------------- check deps
& $py -c "import PyInstaller, PySide6, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[build] missing build dependencies. Install them with:"
    Write-Host "        $py -m pip install pyinstaller PySide6-Essentials pillow pillow-heif pillow-avif-plugin"
    exit 2
}

# ffmpeg is optional for the build but the result is useless without it.
$binDir = Join-Path $repo 'desktop\bin'
foreach ($exe in @('ffmpeg.exe', 'ffprobe.exe')) {
    if (-not (Test-Path (Join-Path $binDir $exe))) {
        Write-Warning "$exe missing in desktop\bin\ -- the packaged app will have no video/audio support."
        Write-Warning "See desktop\bin\README.md for download links."
    }
}

# ---------------------------------------------------------------- clean
if ($Clean) {
    foreach ($d in @($work, (Join-Path $dist 'MediaConv'), $tmp)) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force -ErrorAction SilentlyContinue }
    }
    New-Item -ItemType Directory -Force -Path $tmp, $work | Out-Null
    Write-Host "[build] cleaned previous artifacts"
}

# ---------------------------------------------------------------- build
$spec = Join-Path $repo 'desktop\MediaConv.spec'
if (-not (Test-Path $spec)) { Write-Error "spec not found: $spec"; exit 2 }

Write-Host "[build] running PyInstaller (onedir) ..."
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $py -m PyInstaller --noconfirm --distpath $dist --workpath $work $spec
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("[build] PyInstaller exit={0} elapsed={1:N1}s" -f $code, $sw.Elapsed.TotalSeconds)
if ($code -ne 0) { exit $code }

# ---------------------------------------------------------------- verify
$outDir = Join-Path $dist 'MediaConv'
$outExe = Join-Path $outDir 'MediaConv.exe'
if (-not (Test-Path $outExe)) { Write-Error "missing output: $outExe"; exit 1 }

$size = (Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("[build] OK -> {0}" -f $outExe)
Write-Host ("[build] size = {0:N1} MB" -f ($size / 1MB))

# Smoke test: the packaged exe must be able to report its version.
Write-Host "[build] smoke test ..."
$out = & $outExe version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0 -or $out -notmatch '版本') {
    Write-Warning "smoke test failed: 'MediaConv.exe version' produced no output"
    Write-Warning $out
    exit 1
}
Write-Host ($out.Trim() -split "`n" | Select-Object -First 1)
Write-Host "[build] done"
exit 0
