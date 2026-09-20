<#
  Gera o executável (PyInstaller) e o instalador (Inno Setup) do Jogo do Trem.

  Uso (na raiz do projeto ou em qualquer pasta):
      powershell -ExecutionPolicy Bypass -File instalador\construir.ps1

  Requisitos:
    - .venv criado com Python 3.13:  uv venv --python 3.13 .venv
    - dependências:                  uv pip install --python .venv\Scripts\python.exe -r requirements.txt pyinstaller
    - Inno Setup 6 instalado (winget install JRSoftware.InnoSetup)

  Resultado:
      dist\JogoDoTrem\JogoDoTrem.exe                 (pasta do jogo, roda sem instalar)
      dist\Instalador-JogoDoTrem-<versão>.exe        (instalador)
#>
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Ambiente .venv não encontrado. Veja os requisitos no topo deste script." }

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado. Instale com: winget install JRSoftware.InnoSetup" }

Write-Host "1/4  Gerando o ícone..." -ForegroundColor Cyan
& $python instalador\criar_icone.py

Write-Host "2/4  Gerando o executável (PyInstaller)..." -ForegroundColor Cyan
$ico = (Resolve-Path instalador\icone.ico).Path
& (Join-Path $raiz ".venv\Scripts\pyinstaller.exe") --noconfirm --clean --windowed --name JogoDoTrem `
    --icon $ico --distpath dist --workpath build --specpath instalador jogo_trem.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

Write-Host "3/4  Verificando o pacote (autoteste)..." -ForegroundColor Cyan
$relatorio = Join-Path $env:TEMP "jogo_trem_relatorio.txt"
Remove-Item $relatorio -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "dist\JogoDoTrem\JogoDoTrem.exe" -ArgumentList "--autoteste", "`"$relatorio`"" -Wait -PassThru
if (Test-Path $relatorio) { Get-Content $relatorio }
if ($p.ExitCode -ne 0) { throw "O autoteste do executável falhou." }

Write-Host "4/4  Gerando o instalador (Inno Setup)..." -ForegroundColor Cyan
& $iscc instalador\JogoDoTrem.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }

Write-Host ""
Write-Host "Pronto:" -ForegroundColor Green
Get-ChildItem dist\Instalador-JogoDoTrem-*.exe | ForEach-Object { "  {0}  ({1} MB)" -f $_.FullName, [math]::Round($_.Length / 1MB, 1) }
