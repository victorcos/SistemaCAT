<#
.SYNOPSIS
  Libera o Sistema CAT para as outras máquinas da rede da empresa.

.DESCRIPTION
  Precisa de terminal como ADMINISTRADOR: as duas coisas que faz são do sistema.

  **O diagnóstico que levou a este script.** Em 02/10/2026 o sistema não abria
  de nenhuma outra máquina, nem por cabo nem por Wi-Fi, e o IP não era a causa.
  O Windows tinha o firewall ligado nos três perfis, a rede classificada como
  `Public` — o mais restritivo, que recusa praticamente todo tráfego não
  solicitado — e nenhuma regra de entrada para as portas do sistema. A porta
  escutava em `0.0.0.0` e ninguém de fora chegava nela.

  Duas coisas, então:

    1. a rede da empresa é `Private`, não `Public`. Classificar certo já muda o
       conjunto de regras que o Windows aplica;
    2. uma regra de entrada para a porta da API — **uma só**, porque desde a
       v0.127.0 a API serve o front e a própria API. Antes seriam duas (5173 do
       Vite e 8010 da API).

  O perfil da regra é `Private,Domain` de propósito: ela **não** vale em rede
  pública. Levar o notebook para um café não abre a porta lá.

  O que este script NÃO faz, porque não precisa de administrador:

    cd frontend && npm run build          # o front que a API vai servir
    npm run certificado                   # o par TLS, se os IPs mudaram

  e as três linhas do `backend\.env` que ligam o modo (ver ARQUITETURA §14).

.PARAMETER Porta
  A porta da API. 8010 é o padrão (CAT_API_PORTA).

.PARAMETER Interface
  O adaptador de rede a reclassificar. Sem isto, reclassifica todo adaptador
  que esteja em `Public` — que é o caso comum de quem trocou cabo por Wi-Fi.

.EXAMPLE
  .\scripts\liberar-na-rede.ps1

.EXAMPLE
  .\scripts\liberar-na-rede.ps1 -Porta 8010 -Interface "Wi-Fi 2"
#>
[CmdletBinding()]
param(
    [int]$Porta = 8010,
    [string]$Interface
)

$ErrorActionPreference = "Stop"
$NomeDaRegra = "Sistema CAT (API e front)"

# ---------- exige administrador, e diz como virar um ----------
$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidade)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Este script precisa de administrador." -ForegroundColor Red
    Write-Host "Abra o PowerShell como administrador e rode de novo:"
    Write-Host "  cd '$(Split-Path -Parent $PSScriptRoot)'"
    Write-Host "  .\scripts\liberar-na-rede.ps1 -Porta $Porta"
    exit 1
}

# ---------- 1. a rede da empresa é privada ----------
$perfis = if ($Interface) {
    Get-NetConnectionProfile -InterfaceAlias $Interface
} else {
    Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq "Public" }
}

if (-not $perfis) {
    Write-Host "Nenhum adaptador em 'Public'. Nada a reclassificar." -ForegroundColor DarkGray
} else {
    foreach ($p in $perfis) {
        # DomainAuthenticated não se define à mão: quem o decide é o domínio
        if ($p.NetworkCategory -eq "DomainAuthenticated") {
            Write-Host "  $($p.InterfaceAlias): já autenticada no domínio" -ForegroundColor DarkGray
            continue
        }
        Set-NetConnectionProfile -InterfaceAlias $p.InterfaceAlias -NetworkCategory Private
        Write-Host "  $($p.InterfaceAlias): Public -> Private" -ForegroundColor Green
    }
}

# ---------- 2. a porta da API, e só ela ----------
$existente = Get-NetFirewallRule -DisplayName $NomeDaRegra -ErrorAction SilentlyContinue
if ($existente) {
    # refaz em vez de somar: rodar duas vezes não pode deixar duas regras
    Remove-NetFirewallRule -DisplayName $NomeDaRegra
    Write-Host "  regra anterior removida" -ForegroundColor DarkGray
}
New-NetFirewallRule -DisplayName $NomeDaRegra `
    -Description "Entrada da API do Sistema CAT, que serve tambem o front. Nao vale em rede publica." `
    -Direction Inbound -Protocol TCP -LocalPort $Porta `
    -Profile Private, Domain -Action Allow | Out-Null
Write-Host "  entrada TCP $Porta liberada em Private,Domain" -ForegroundColor Green

# ---------- 3. o que dizer para o pessoal ----------
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "172.1*" -and $_.IPAddress -notlike "172.2*" } |
    Select-Object -ExpandProperty IPAddress
$nome = [System.Net.Dns]::GetHostName()

Write-Host ""
Write-Host "Pronto. Os endereços para o pessoal:" -ForegroundColor Cyan
Write-Host "  https://${nome}:$Porta   <- sobrevive à troca de IP; prefira este"
foreach ($ip in $ips) { Write-Host "  https://${ip}:$Porta" }
Write-Host ""
Write-Host "Se ainda não abrir, falta o lado que não é de administrador:" -ForegroundColor Yellow
Write-Host "  cd frontend; npm run build"
Write-Host "  e as tres linhas CAT_PASTA_DO_FRONT / CAT_TLS_* no backend\.env (ARQUITETURA §14),"
Write-Host "  depois reiniciar a API."
Write-Host ""
Write-Host "O certificado é autoassinado: a primeira visita avisa, e prosseguir" -ForegroundColor DarkGray
Write-Host "dá contexto seguro de verdade. Se os IPs mudaram, refaça-o antes:" -ForegroundColor DarkGray
Write-Host "  cd frontend; npm run certificado -- --refazer" -ForegroundColor DarkGray
