<#
.SYNOPSIS
  Para o Sistema CAT: motor, fila, API e tela. O banco em Docker fica de pé.

.DESCRIPTION
  Fechar as quatro janelas à mão funciona, mas deixa restos: no Windows,
  encerrar o PowerShell que abriu o processo NÃO encerra o filho. Já
  aconteceu de sobrar um neto órfão do uvicorn segurando a 8020 — o socket
  continua LISTENING atribuído a um PID morto e o HTTP continua respondendo
  código velho (24/09/2026).

  Por isso aqui se para por PORTA, não por janela: quem responde é quem morre.
  Depois fecham-se as janelas que sobraram.

  O Postgres (55432) NÃO é tocado: é container Docker, sobe sozinho com a
  máquina e é compartilhado. Derrubá-lo obrigaria a esperar o healthcheck de
  novo na próxima subida, sem ganho nenhum.

.EXAMPLE
  .\scripts\parar.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$PORTAS = @{ 8020 = "motor"; 8010 = "API"; 5173 = "tela" }

Write-Host ""
Write-Host "  Parando o Sistema CAT" -ForegroundColor Cyan
Write-Host "  ─────────────────────" -ForegroundColor DarkGray

$mortos = 0
foreach ($porta in $PORTAS.Keys | Sort-Object) {
    $conns = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host ("  {0,-6} {1,-6} já parado" -f $porta, $PORTAS[$porta]) -ForegroundColor DarkGray
        continue
    }
    foreach ($pid_ in ($conns.OwningProcess | Sort-Object -Unique)) {
        $p = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
        $nome = if ($p) { $p.ProcessName } else { "(PID morto)" }
        try {
            Stop-Process -Id $pid_ -Force -ErrorAction Stop
            Write-Host ("  {0,-6} {1,-6} encerrado: {2} (PID {3})" -f $porta, $PORTAS[$porta], $nome, $pid_) -ForegroundColor Green
            $mortos++
        } catch {
            Write-Host ("  {0,-6} {1,-6} não encerrou: {2}" -f $porta, $PORTAS[$porta], $_.Exception.Message) -ForegroundColor Yellow
        }
    }
}

# A FILA não escuta porta nenhuma: parar por porta nunca a alcança, e ela fica
# rodando etapa com o resto do sistema derrubado.
$fila = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'workers\.rodar' }
foreach ($f in $fila) {
    try {
        Stop-Process -Id $f.ProcessId -Force -ErrorAction Stop
        Write-Host "  fila   encerrada (PID $($f.ProcessId))" -ForegroundColor Green
        $mortos++
    } catch { }
}

# O NETO ÓRFÃO do uvicorn: filho do reloader, sobrevive à morte do pai e
# continua segurando a 8020 — o socket fica atribuído a um PID já morto.
# Procurar por 'cat' na linha de comando NÃO funciona: o órfão roda pelo
# Python do sistema e sua linha é só `spawn_main(parent_pid=...)`. O que o
# identifica é o pai não existir mais.
$spawns = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -match 'multiprocessing\.spawn' }
foreach ($o in $spawns) {
    $pai = Get-Process -Id $o.ParentProcessId -ErrorAction SilentlyContinue
    if ($pai) { continue }        # pai vivo: é processo legítimo em uso
    try {
        Stop-Process -Id $o.ProcessId -Force -ErrorAction Stop
        Write-Host "  órfão do uvicorn encerrado (PID $($o.ProcessId), pai $($o.ParentProcessId) morto)" -ForegroundColor Green
        $mortos++
    } catch { }
}

# as janelas que o subir.ps1 abriu, se sobraram vazias
$janelas = Get-Process powershell, pwsh -ErrorAction SilentlyContinue |
           Where-Object { $_.MainWindowTitle -like "Sistema CAT*" }
foreach ($j in $janelas) {
    try {
        Stop-Process -Id $j.Id -Force -ErrorAction Stop
        Write-Host "  janela fechada: $($j.MainWindowTitle)" -ForegroundColor DarkGray
    } catch { }
}

Start-Sleep -Seconds 1
$restou = @(8020, 8010, 5173) | Where-Object {
    Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue
}
Write-Host ""
if ($restou) {
    Write-Host "  ainda no ar: porta $($restou -join ', ')" -ForegroundColor Yellow
    Write-Host "  Rode de novo, ou olhe quem é: Get-NetTCPConnection -LocalPort $($restou[0])" -ForegroundColor Yellow
} else {
    Write-Host "  tudo parado. O Postgres (55432) segue de pé, de propósito." -ForegroundColor Green
}
Write-Host ""
