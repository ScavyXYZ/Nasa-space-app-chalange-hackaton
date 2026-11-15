param([int]$Port = 8003, [switch]$Build)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ($Build -or -not (Test-Path "frontend/dist/index.html")) {
        npm --prefix frontend run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    python scripts/prepare_runtime_data.py
    if ($LASTEXITCODE -ne 0) { throw "Runtime data verification failed" }
    Write-Host "Local demo: http://127.0.0.1:$Port/"
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like "Wi-Fi*" -and $_.IPAddress -notlike "169.254.*" } |
        ForEach-Object { Write-Host "Phone on same Wi-Fi: http://$($_.IPAddress):$Port/" }
    Write-Host "Keep this window open. Public access needs a separate tunnel."
    python -m uvicorn backend.main:app --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
