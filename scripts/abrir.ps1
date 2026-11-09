<#
.SYNOPSIS
  Abre o Sistema CAT: sobe o que faltar e leva você à tela. É o atalho de um clique.

.DESCRIPTION
  O `subir.ps1` recusa subir quando alguma porta já está ocupada, e com razão:
  duas cópias no ar fazem a tela falar com o processo errado sem nenhum aviso.
  Mas num atalho de clique único isso vira beco sem saída — quem clica duas
  vezes no dia recebe um erro vermelho em vez da tela.

  Este script resolve o caso comum antes de chegar lá:

    já está no ar  -> abre o navegador e pronto;
    está parado    -> chama o `subir.ps1` e abre o navegador;
    está pela metade (alguma porta sim, outra não) -> avisa o que falta e
                      manda parar antes, em vez de subir por cima.

  Quem decide se "está no ar" é o `/api/saude`, não a porta: porta aberta por
  processo travado responde ao netstat e não responde à tela.

.EXAMPLE
  .\scripts\abrir.ps1
#>
[CmdletBinding()]
param([switch]$SemNavegador)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$tela = "http://localhost:5173"
$saude = "https://localhost:8010/api/saude"

function Escuta([int]$porta) {
    [bool](Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue)
}

function Responde([string]$url, [int]$segundos = 5) {
    try {
        # -SkipCertificateCheck: a API de dev usa certificado próprio
        $r = Invoke-WebRequest -Uri $url -TimeoutSec $segundos -SkipCertificateCheck `
             -ErrorAction Stop
        return $r.StatusCode -eq 200
    } catch { return $false }
}

Write-Host ""
Write-Host "  Sistema CAT" -ForegroundColor Cyan
Write-Host "  ───────────" -ForegroundColor DarkGray

# ------------------------------------------------------------------ já no ar?
if (Responde $saude) {
    try {
        $s = (Invoke-WebRequest -Uri $saude -TimeoutSec 5 -SkipCertificateCheck).Content |
             ConvertFrom-Json
        Write-Host "  já está no ar — API $($s.versao), motor $($s.motor.versao)" -ForegroundColor Green
    } catch {
        Write-Host "  já está no ar" -ForegroundColor Green
    }
    if (-not $SemNavegador) { Start-Process $tela }
    Write-Host "  tela: $tela" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# ---------------------------------------------------------- pela metade?
$noAr = @(8020, 8010, 5173) | Where-Object { Escuta $_ }
if ($noAr) {
    Write-Host "  estado inconsistente: porta $($noAr -join ', ') no ar, mas /api/saude não responde." -ForegroundColor Yellow
    Write-Host "  Isso é cópia velha travada ou subida pela metade — subir por cima faria a" -ForegroundColor Yellow
    Write-Host "  tela conversar com o processo errado." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Rode antes:  .\scripts\parar.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# ------------------------------------------------------------------- subir
Write-Host "  parado — subindo" -ForegroundColor Cyan
Write-Host ""
& (Join-Path $PSScriptRoot "subir.ps1") -SemNavegador
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  o subir.ps1 não concluiu. Veja a mensagem acima." -ForegroundColor Red
    Write-Host ""
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "  esperando a API responder..." -NoNewline -ForegroundColor DarkGray
$ok = $false
foreach ($i in 1..40) {
    Start-Sleep -Seconds 3
    if (Responde $saude 3) { $ok = $true; break }
    Write-Host "." -NoNewline -ForegroundColor DarkGray
}
Write-Host ""
if ($ok) {
    try {
        $s = (Invoke-WebRequest -Uri $saude -TimeoutSec 5 -SkipCertificateCheck).Content |
             ConvertFrom-Json
        $versao = Get-Content (Join-Path $raiz "VERSAO") -ErrorAction SilentlyContinue
        Write-Host "  no ar — API $($s.versao), motor $($s.motor.versao), repo $versao" -ForegroundColor Green
        if ($s.versao -ne $s.motor.versao) {
            # um servindo código velho é erro silencioso: a tela funciona e
            # entrega número errado
            Write-Host "  !! API e motor em versões diferentes" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  no ar" -ForegroundColor Green
    }
    if (-not $SemNavegador) { Start-Process $tela }
} else {
    Write-Host "  a API não respondeu em 2 minutos." -ForegroundColor Red
    Write-Host "  Olhe a janela 'Sistema CAT — API': costuma ser erro de compilação." -ForegroundColor Red
}
Write-Host "  tela: $tela" -ForegroundColor DarkGray
Write-Host ""
