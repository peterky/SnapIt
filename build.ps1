$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"
& $Python -m pip install -q -r requirements.txt
& $Python -m pip install -q pyinstaller

& $Python -m PyInstaller `
    --noconsole `
    --onefile `
    --name SnapIt `
    --clean `
    --collect-all pystray `
    --collect-all keyboard `
    --hidden-import win32timezone `
    --hidden-import win32clipboard `
    --hidden-import win32gui `
    --hidden-import win32ui `
    --hidden-import win32con `
    --paths . `
    snapit\__main__.py

Write-Host ""
Write-Host "Built: $ProjectRoot\dist\SnapIt.exe" -ForegroundColor Green
Write-Host "Run dist\SnapIt.exe or enable 'Start with Windows' in Settings." -ForegroundColor Cyan