<#
.SYNOPSIS
  Instala o Sistema CAT numa máquina Windows nova, do zero até o primeiro login.

.DESCRIPTION
  Roda de dentro do repositório clonado (qualquer pasta). Faz, nesta ordem:

    1. confere os pré-requisitos: git, Python 3.11+, Node 20+, .NET 10 SDK,
       Docker (opcional);
    2. cria o ambiente Python em backend\.venv e instala o backend;
    3. cria backend\.env a partir de .env.example, com JWT e pimenta NOVOS
       (segredos de servidor não viajam entre máquinas) e a pasta de trabalho
       em disco local;
    4. sobe o Postgres em Docker (porta 55432). Sem Docker, usa SQLite;
    5. aplica as migrações e cria os três gestores iniciais — as senhas
       provisórias saem no terminal, uma vez só;
    6. compila a API em C# (dotnet build);
    7. instala o front (npm install).

  É idempotente: rodar de novo não apaga .env, banco nem senhas.

.PARAMETER InstalarPreRequisitos
  Instala o que faltar via winget (Git, Python, Node LTS, .NET 10 SDK).
  Docker Desktop não entra aqui: pede reinício e conta própria.

.EXAMPLE
  gh repo clone victorcos/SistemaCAT
  cd SistemaCAT
  .\scripts\instalar.ps1
  .\scripts\subir.ps1
#>
[CmdletBinding()]
param(
    [switch]$InstalarPreRequisitos,
    [switch]$SemDocker
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$frontend = Join-Path $raiz "frontend"

function Passo([string]$texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Ok([string]$texto)    { Write-Host "    $texto" -ForegroundColor Green }
function Aviso([string]$texto) { Write-Host "    $texto" -ForegroundColor Yellow }

function Tem([string]$comando) {
    return [bool](Get-Command $comando -ErrorAction SilentlyContinue)
}

# Comando nativo que falha não derruba o script sozinho no PowerShell 5.1:
# $ErrorActionPreference não olha o código de saída. Aqui olha.
function Rodar([string]$descricao, [scriptblock]$bloco) {
    & $bloco
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $descricao (código $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- 1. pré-requisitos
Passo "Pré-requisitos"
$faltam = @()
if (-not (Tem git))    { $faltam += "Git.Git" }
if (-not (Tem node))   { $faltam += "OpenJS.NodeJS.LTS" }
# a API em C# fixa o SDK em api\global.json; ter só o .NET 8 não serve
if (-not (Tem dotnet) -or -not ((dotnet --list-sdks) -match "^10\.")) { $faltam += "Microsoft.DotNet.SDK.10" }
$python = $null
foreach ($candidato in @("py -3.14", "py -3.13", "py -3.12", "py -3.11", "python")) {
    $exe, $arg = $candidato.Split(" ", 2)
    if (-not (Tem $exe)) { continue }
    try {
        $versao = & $exe $arg -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($versao -and [version]$versao -ge [version]"3.11") { $python = $candidato; break }
    } catch { }
}
if (-not $python) { $faltam += "Python.Python.3.12" }

if ($faltam.Count -gt 0) {
    if ($InstalarPreRequisitos) {
        foreach ($pacote in $faltam) {
            Passo "winget install $pacote"
            winget install --id $pacote -e --accept-package-agreements --accept-source-agreements
        }
        Aviso "Feche e abra o terminal para o PATH atualizar, e rode este script de novo."
        exit 0
    }
    Write-Host "    Falta instalar: $($faltam -join ', ')" -ForegroundColor Red
    Write-Host "    Rode com -InstalarPreRequisitos, ou instale à mão:"
    foreach ($pacote in $faltam) { Write-Host "      winget install --id $pacote -e" }
    exit 1
}
$pyExe, $pyArg = $python.Split(" ", 2)
Ok "git, node, .NET 10 e Python ($python) encontrados"

$docker = (-not $SemDocker) -and (Tem docker)
if ($docker) {
    # Nao usar try/catch com `docker info *> $null`: no PowerShell 5.1 redirecionar
    # o stderr de um executavel nativo vira NativeCommandError e, com
    # $ErrorActionPreference = "Stop", cai no catch ate quando o docker responde.
    # Perguntar a versao do servidor: so o daemon no ar sabe responder.
    $versaoDocker = (docker info --format "{{.ServerVersion}}" 2>$null | Select-Object -Last 1)
    if ($versaoDocker -and $versaoDocker -notmatch "error|cannot find") {
        Ok "Docker em execução (servidor $versaoDocker)"
    } else {
        $docker = $false
        Aviso "Docker instalado mas não está rodando: vou usar SQLite"
    }
} else {
    Aviso "Sem Docker: o banco será SQLite (serve para desenvolver; Postgres é o de produção)"
}

# ---------------------------------------------------------------- 2. backend
Passo "Ambiente Python em backend\.venv"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pyExe $pyArg -m venv (Join-Path $backend ".venv")
}
Rodar "atualizar o pip" { & $venvPython -m pip install --quiet --upgrade pip }
Push-Location $backend
try {
    Rodar "instalar o backend (pip install -e)" { & $venvPython -m pip install --quiet -e ".[dev]" }
} finally { Pop-Location }
Ok "backend instalado"

# ---------------------------------------------------------------- 3. .env
Passo "backend\.env"
$env_ = Join-Path $backend ".env"
if (Test-Path $env_) {
    Ok ".env já existe — mantido (segredos e pimenta não se trocam por acidente)"
} else {
    $segredo = & $venvPython -c "import secrets; print(secrets.token_urlsafe(48))"
    $pimenta = & $venvPython -c "import secrets; print(secrets.token_urlsafe(32))"
    $trabalho = Join-Path $backend "data\trabalho"
    New-Item -ItemType Directory -Force $trabalho | Out-Null
    $bancoUrl = if ($docker) { "postgresql+psycopg://cat:cat@localhost:55432/cat" }
                else { "sqlite:///./data/cat.db" }
    @"
# Ambiente do Sistema CAT nesta máquina. NAO versionar este arquivo.
# Gerado por scripts\instalar.ps1 em $(Get-Date -Format "dd/MM/yyyy HH:mm").

CAT_BANCO_URL=$bancoUrl

# Segredo do token, gerado aqui. Trocar invalida as sessoes abertas.
CAT_JWT_SEGREDO=$segredo
CAT_JWT_MINUTOS=480

# Pimenta da senha, gerada aqui. Trocar invalida TODAS as senhas.
CAT_SENHA_PIMENTA=$pimenta

CAT_LOG_NIVEL=INFO
CAT_ORIGENS_PERMITIDAS=http://localhost:5173

# Rascunho das execucoes (parquets). Disco local, de proposito.
CAT_PASTA_DE_TRABALHO=$trabalho
CAT_MEMORIA_ANALITICA=4GB
CAT_THREADS_ANALITICAS=4
"@ | Set-Content -Path $env_ -Encoding UTF8
    Ok ".env criado com segredos novos; pasta de trabalho em $trabalho"
}

# ---------------------------------------------------------------- 4. banco
if ($docker) {
    Passo "Postgres em Docker (porta 55432)"
    Rodar "subir o Postgres" { docker compose -f (Join-Path $raiz "docker\docker-compose.yml") up -d }
    $tentativas = 0
    do {
        Start-Sleep -Seconds 2
        $saude = docker inspect --format "{{.State.Health.Status}}" docker-banco-1 2>$null
        $tentativas++
    } while ($saude -ne "healthy" -and $tentativas -lt 30)
    if ($saude -ne "healthy") { throw "O Postgres não ficou saudável em 60 s. Veja: docker compose -f docker\docker-compose.yml logs" }
    Ok "Postgres no ar"
}

# ---------------------------------------------------------------- 5. esquema e gestores
Passo "Migrações e gestores iniciais"
Push-Location $backend
try {
    Rodar "aplicar as migrações" { & $venvPython -m alembic upgrade head }
    Ok "esquema em dia"
    Write-Host ""
    Rodar "criar os gestores iniciais" { & $venvPython -m cat.apresentacao.cli.semear }
} finally { Pop-Location }

# ---------------------------------------------------------------- 6. API em C#
Passo "API em C# (dotnet build)"
Push-Location (Join-Path $raiz "api")
try { Rodar "compilar a API" { dotnet build SistemaCat.slnx --nologo -v q } } finally { Pop-Location }
Ok "API compilada"

# ---------------------------------------------------------------- 7. front
Passo "Front (npm install)"
Push-Location $frontend
try { Rodar "npm install" { npm install --no-fund --no-audit } } finally { Pop-Location }
Ok "front instalado"

Write-Host ""
Write-Host "Pronto. Para subir o motor, a API e a tela:" -ForegroundColor Cyan
Write-Host "    .\scripts\subir.ps1"
Write-Host "Depois: http://localhost:5173 (tela) e http://localhost:8010/docs (API)."
Write-Host "Primeiro acesso com um dos gestores acima; a troca de senha é obrigatória."
