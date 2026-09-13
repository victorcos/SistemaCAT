<#
.SYNOPSIS
  Sobe o motor, a API e a tela do Sistema CAT, cada um na sua janela, e abre o navegador.

.DESCRIPTION
  Três processos, nesta ordem:

    1. motor Python em http://127.0.0.1:8020 — só aceita conexão da própria
       máquina; faz o trabalho pesado e atende o que ainda não foi portado;
    2. API em C# em http://localhost:8010 — a única porta que a tela conhece;
       repassa ao motor o que ainda não foi migrado (docs/MIGRACAO_CSHARP.md);
    3. tela em http://localhost:5173 (Vite).

  Os três recarregam sozinhos ao salvar código. Se o banco for o Postgres em
  Docker e ele estiver parado, sobe antes. Fechar as janelas derruba tudo.

.EXAMPLE
  .\scripts\subir.ps1
#>
[CmdletBinding()]
param([switch]$SemNavegador)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$frontend = Join-Path $raiz "frontend"
$api = Join-Path $raiz "api\src\Cat.Api"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Ambiente não instalado. Rode antes: .\scripts\instalar.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "Falta o .NET 10 SDK. Rode: .\scripts\instalar.ps1 -InstalarPreRequisitos" -ForegroundColor Red
    exit 1
}

# porta ocupada é quase sempre uma cópia antiga ainda no ar; subir por cima
# faria a tela falar com o processo errado sem nenhum aviso
$ocupadas = foreach ($porta in 8020, 8010, 5173) {
    if (Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue) { $porta }
}
if ($ocupadas) {
    Write-Host "Porta ocupada: $($ocupadas -join ', '). Feche o que já está no ar antes de subir de novo." -ForegroundColor Red
    exit 1
}

# o banco em Docker precisa estar de pé antes do motor e da API
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

Write-Host "==> Motor em http://127.0.0.1:8020 (só local)" -ForegroundColor Cyan
Janela "Sistema CAT — motor" $backend "& '$venvPython' -m uvicorn cat.apresentacao.api.app:app --reload --host 127.0.0.1 --port 8020"

Write-Host "==> API em http://localhost:8010" -ForegroundColor Cyan
Janela "Sistema CAT — API" $api "dotnet watch run --non-interactive --no-launch-profile"

Write-Host "==> Tela em http://localhost:5173" -ForegroundColor Cyan
Janela "Sistema CAT — tela" $frontend "npm run dev"

if (-not $SemNavegador) {
    Start-Sleep -Seconds 8
    Start-Process "http://localhost:5173"
}
Write-Host "Feche as três janelas para parar. Quem está no ar, e com qual versão: http://localhost:8010/api/saude."
