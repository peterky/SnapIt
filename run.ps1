$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Start-Process -FilePath ".\.venv\Scripts\pythonw.exe" -ArgumentList "-m", "snapit" -WindowStyle Hidden

Write-Host "SnapIt started in the background (check system tray)." -ForegroundColor Green