param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
& .\.venv\Scripts\python.exe -m unittest discover -s tests
& .\.venv\Scripts\python.exe -m compileall app
& .\.venv\Scripts\pyinstaller.exe --onefile --name anime-sub-ai --add-data "app/web/templates;app/web/templates" app/__main__.py

$PackageDir = Join-Path $Root "dist\anime-sub-ai-windows"
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
Copy-Item "dist\anime-sub-ai.exe" $PackageDir -Force
Copy-Item "README.md" $PackageDir -Force
Copy-Item "config.yaml" $PackageDir -Force
Copy-Item "CHANGELOG.md" $PackageDir -Force

$ZipPath = Join-Path $Root "dist\anime-sub-ai-windows.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$PackageDir\*" -DestinationPath $ZipPath
Write-Host "Built $ZipPath"
