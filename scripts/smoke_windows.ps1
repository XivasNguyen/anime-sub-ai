param(
    [string]$Executable = "python -m app"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Executable -eq "python -m app") {
    python -m app --help | Out-Host
    python -m unittest discover -s tests
    python -m compileall app
} else {
    & $Executable --help | Out-Host
}

python -c "from app.utils.subprocess_runner import command_available; print({'ffmpeg': command_available('ffmpeg'), 'mkvmerge': command_available('mkvmerge'), 'mkvextract': command_available('mkvextract')})"
Write-Host "Smoke completed."
