<#
.SYNOPSIS
  Sobe a API e a tela do Sistema CAT, cada uma na sua janela, e abre o navegador.

.DESCRIPTION
  API em http://localhost:8010 (uvicorn com recarga automática) e tela em
  http://localhost:5173 (Vite). Se o banco for o Postgres em Docker e ele
  estiver parado, sobe antes. Fechar as janelas derruba os dois.

.EXAMPLE
  .\scripts\subir.ps1
#>
[CmdletBinding()]
param([switch]$SemNavegador)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$frontend = Join-Path $raiz "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Ambiente não instalado. Rode antes: .\scripts\instalar.ps1" -ForegroundColor Red
    exit 1
}

# o banco em Docker precisa estar de pé antes da API
$env_ = Get-Content (Join-Path $backend ".env") -ErrorAction SilentlyContinue
if ($env_ -match "^CAT_BANCO_URL=postgresql" -and (Get-Command docker -ErrorAction SilentlyContinue)) {
    $estado = docker inspect --format "{{.State.Status}}" docker-banco-1 2>$null
    if ($estado -ne "running") {
        Write-Host "==> Subindo o Postgres" -ForegroundColor Cyan
        docker compose -f (Join-Path $raiz "docker\docker-compose.yml") up -d
        Start-Sleep -Seconds 5
    }
}

function Janela([string]$titulo, [string]$pasta, [string]$comando) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle = '$titulo'; Set-Location '$pasta'; $comando"
    )
}

Write-Host "==> API em http://localhost:8010 (recarga automática)" -ForegroundColor Cyan
Janela "Sistema CAT — API" $backend "& '$venvPython' -m uvicorn cat.apresentacao.api.app:app --reload --host 0.0.0.0 --port 8010"

Write-Host "==> Tela em http://localhost:5173" -ForegroundColor Cyan
Janela "Sistema CAT — tela" $frontend "npm run dev"

if (-not $SemNavegador) {
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:5173"
}
Write-Host "Feche as duas janelas para parar. A versão que está no ar aparece em http://localhost:8010/api/saude."
