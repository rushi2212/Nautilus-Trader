$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js and npm are required. Install the current Node.js LTS release, then run start.ps1 again.'
}

if (-not (Test-Path -LiteralPath (Join-Path $backendDir '.env'))) {
    Copy-Item -LiteralPath (Join-Path $backendDir '.env.example') -Destination (Join-Path $backendDir '.env')
    Write-Host 'Created backend\.env. Add your GROQ_API_KEY there to enable Groq chat.' -ForegroundColor Yellow
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv (Join-Path $backendDir '.venv') }
    else { & python -m venv (Join-Path $backendDir '.venv') }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

Write-Host 'Installing/checking FastAPI dependencies…' -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $backendDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed. See the error above.' }

Write-Host 'Installing/checking React dependencies…' -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
    Push-Location $frontendDir
    try { & npm install; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. See the error above.' } }
    finally { Pop-Location }
}

function Test-LocalUrl([string]$url) {
    try { Invoke-WebRequest -Uri $url -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}

$apiScript = Join-Path $backendDir 'run-api.ps1'
$uiScript = Join-Path $frontendDir 'run-ui.ps1'
if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$apiScript`"")
    Write-Host 'Starting FastAPI…' -ForegroundColor Cyan
} else { Write-Host 'FastAPI is already running.' -ForegroundColor Gray }

if (-not (Test-LocalUrl 'http://127.0.0.1:5173')) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$uiScript`"")
    Write-Host 'Starting the React dashboard…' -ForegroundColor Cyan
} else { Write-Host 'The React dashboard is already running.' -ForegroundColor Gray }

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ((Test-LocalUrl 'http://127.0.0.1:8000/api/health') -and (Test-LocalUrl 'http://127.0.0.1:5173')) { break }
    Start-Sleep -Seconds 1
}
if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) { throw 'FastAPI did not start. Check the API PowerShell window for details.' }
if (-not (Test-LocalUrl 'http://127.0.0.1:5173')) { throw 'The React dashboard did not start. Check the UI PowerShell window for details.' }

Start-Process 'http://127.0.0.1:5173'
Write-Host 'Dashboard: http://127.0.0.1:5173 | API docs: http://127.0.0.1:8000/docs' -ForegroundColor Green
Write-Host 'Keep both PowerShell windows open while using the app.' -ForegroundColor Gray

