# ============================================================
# Total Support · 풀스택 단일 실행 (PowerShell)
# ============================================================
# 사용:
#   .\scripts\run_stack.ps1                  # API + SPA 동시 (8000 포트)
#   .\scripts\run_stack.ps1 -Port 9000       # 포트 override
#   .\scripts\run_stack.ps1 -Reload          # 코드 변경 자동 반영
#
# 접속:
#   - SPA  : http://localhost:8000/ui/   (자동 LIVE 모드)
#   - API  : http://localhost:8000/api/grant/...
#   - Docs : http://localhost:8000/api/grant/docs
# ============================================================

param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$backend = Split-Path -Parent $here

Push-Location $backend
try {
    $venv = Join-Path $backend ".venv\Scripts\python.exe"
    if (-not (Test-Path $venv)) {
        Write-Error "venv가 없습니다: $venv  먼저 'python -m venv .venv' 실행하세요."
    }

    $args = @(
        "-m", "uvicorn",
        "total_support.api.main:app",
        "--host", "127.0.0.1",
        "--port", "$Port"
    )
    if ($Reload) { $args += "--reload" }

    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host " Total Support · LIVE STACK" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host " SPA      : http://localhost:$Port/ui/" -ForegroundColor Green
    Write-Host " API ping : http://localhost:$Port/api/grant/ping" -ForegroundColor Green
    Write-Host " Docs     : http://localhost:$Port/api/grant/docs" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""

    & $venv $args
}
finally {
    Pop-Location
}
