<#
.SYNOPSIS
  Cria na Área de Trabalho os atalhos "Sistema CAT" e "Sistema CAT - Parar".

.DESCRIPTION
  Roda uma vez por máquina. Os atalhos apontam para `abrir.ps1` e `parar.ps1`
  desta cópia do repositório — o caminho é resolvido na hora da criação, então
  mover a pasta exige rodar de novo.

  `-ExecutionPolicy Bypass` no atalho é necessário: a política padrão do
  Windows recusa script não assinado, e o atalho morreria calado numa janela
  que pisca e fecha. `-NoExit` mantém a janela aberta para a mensagem ser
  lida — sem ele, erro de subida some antes de alguém ver.

.EXAMPLE
  .\scripts\atalhos.ps1
#>
[CmdletBinding()]
param([string]$Pasta)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
if (-not $Pasta) { $Pasta = [Environment]::GetFolderPath("Desktop") }
if (-not (Test-Path $Pasta)) {
    Write-Host "Pasta não encontrada: $Pasta" -ForegroundColor Red
    exit 1
}

$itens = @(
    @{ Nome = "Sistema CAT.lnk"
       Script = "abrir.ps1"
       Desc = "Sobe o Sistema CAT e abre a tela"
       Icone = "shell32.dll,137" },
    @{ Nome = "Sistema CAT - Parar.lnk"
       Script = "parar.ps1"
       Desc = "Para motor, fila, API e tela (o banco fica de pé)"
       Icone = "shell32.dll,132" }
)

Write-Host ""
Write-Host "  Atalhos em: $Pasta" -ForegroundColor Cyan
$ws = New-Object -ComObject WScript.Shell
try {
    foreach ($i in $itens) {
        $script = Join-Path $raiz "scripts\$($i.Script)"
        if (-not (Test-Path $script)) {
            Write-Host "  !! não encontrei $script" -ForegroundColor Red
            continue
        }
        $alvo = Join-Path $Pasta $i.Nome
        $lnk = $ws.CreateShortcut($alvo)
        $lnk.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        $lnk.Arguments = "-ExecutionPolicy Bypass -NoExit -File `"$script`""
        $lnk.WorkingDirectory = $raiz
        $lnk.Description = $i.Desc
        $lnk.IconLocation = $i.Icone
        $lnk.WindowStyle = 1
        $lnk.Save()
        Write-Host "  criado: $($i.Nome)" -ForegroundColor Green
    }
} finally {
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ws) | Out-Null
}
Write-Host ""
Write-Host "  Aponta para esta cópia: $raiz" -ForegroundColor DarkGray
Write-Host "  Mover a pasta exige rodar este script de novo." -ForegroundColor DarkGray
Write-Host ""
