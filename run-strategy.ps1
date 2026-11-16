$ErrorActionPreference = 'Stop'
$backendDir = Join-Path $PSScriptRoot 'backend'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment missing. Run .\start.ps1 first to install dependencies.'
}
Push-Location $backendDir
try {
    & $python run-strategy.py
    if ($LASTEXITCODE -ne 0) { throw "Nautilus strategy runner exited with code $LASTEXITCODE." }
}
finally { Pop-Location }
