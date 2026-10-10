# Build the Windows installer with Inno Setup.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-installer.ps1
# NOTE: pure ASCII on purpose -- Windows PowerShell 5.1 reads .ps1 as ANSI/GBK.
param(
    [switch]$SkipPortable
)

$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
$ws   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dist = Join-Path $proj 'dist'
$iscc = Join-Path $ws 'tools\innosetup\ISCC.exe'
$portable = Join-Path $dist 'MediaConv'

if (-not (Test-Path $iscc)) { Write-Error "ISCC not found: $iscc"; exit 2 }

if (-not $SkipPortable -and -not (Test-Path (Join-Path $portable 'MediaConv.exe'))) {
    Write-Host "[installer] portable build missing; running build-desktop.ps1 first"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build-desktop.ps1')
}

# Ship the user guide and license next to the exe so the installer can include them.
Copy-Item (Join-Path $proj 'docs\使用说明.txt') (Join-Path $portable '使用说明.txt') -Force
if (Test-Path (Join-Path $proj 'docs\版本说明.txt')) {
    Copy-Item (Join-Path $proj 'docs\版本说明.txt') (Join-Path $portable '版本说明.txt') -Force
}

Write-Host "[installer] running Inno Setup compiler ..."
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $iscc (Join-Path $PSScriptRoot 'installer.iss')
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("[installer] ISCC exit={0} elapsed={1:N1}s" -f $code, $sw.Elapsed.TotalSeconds)
if ($code -ne 0) { exit $code }

$setup = Get-ChildItem $dist -Filter 'MediaConv-Setup-*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($setup) {
    Write-Host ("[installer] OK -> {0}" -f $setup.FullName)
    Write-Host ("[installer] size = {0:N1} MB" -f ($setup.Length / 1MB))
}
exit 0
