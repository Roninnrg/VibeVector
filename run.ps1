# «Вектор» — запуск одной командой (Windows / PowerShell).
#
#   .\run.ps1                 первый запуск: venv, зависимости, ffmpeg, модели, демо
#   .\run.ps1 -Fast           без скачивания моделей (демо-лекции работают сразу)
#   .\run.ps1 -Port 8080      другой порт
#   .\run.ps1 -NoBrowser      не открывать браузер
#   .\run.ps1 -Recreate       пересоздать виртуальное окружение
#
# После первого запуска повторный старт занимает пару секунд: все проверки
# идемпотентны и пропускают уже установленное.

[CmdletBinding()]
param(
    [switch]$Fast,
    [switch]$NoBrowser,
    [switch]$Recreate,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "."
$env:VECTOR_PORT = "$Port"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3.10+ не найден. Установите Python с https://www.python.org/downloads/ и включите «Add to PATH»."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if ($Recreate -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".venv"))) {
    Write-Step "Удаляю старое виртуальное окружение"
    Remove-Item -LiteralPath (Join-Path $PSScriptRoot ".venv") -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $base = Resolve-Python
    Write-Step "Создаю виртуальное окружение .venv"
    $baseArgs = @()
    if ($base.Length -gt 1) { $baseArgs = $base[1..($base.Length - 1)] }
    & $base[0] @baseArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать .venv" }

    Write-Step "Устанавливаю зависимости"
    & $venvPython -m pip install --upgrade pip --quiet
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Не удалось установить зависимости" }
}

Write-Step "Проверяю ffmpeg / ffprobe"
& $venvPython scripts/setup_tools.py
if ($LASTEXITCODE -ne 0) { throw "ffmpeg не готов (см. сообщение выше)" }

if ($Fast) {
    Write-Host "  · режим -Fast: модели не скачиваются, доступны только демо-лекции" -ForegroundColor Yellow
    Write-Host "    для загрузки новых видео запустите scripts/download_models.py" -ForegroundColor Yellow
} else {
    Write-Step "Проверяю офлайн-модели (Whisper + эмбеддинги, ~1.2 ГБ при первом запуске)"
    & $venvPython scripts/download_models.py
    if ($LASTEXITCODE -ne 0) { throw "Модели не готовы (см. сообщение выше)" }
}

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "data\vector.db"))) {
    Write-Step "Готовлю демонстрационные лекции"
    & $venvPython scripts/seed_demo.py
    if ($LASTEXITCODE -ne 0) { throw "Не удалось восстановить демо-лекции" }
} else {
    Write-Host "  · база data/vector.db уже есть"
}

$url = "http://127.0.0.1:$Port"
Write-Step "Запускаю «Вектор» на $url"
Write-Host "  Ctrl+C — остановить сервер"
if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($Target)
        Start-Sleep -Seconds 2
        Start-Process $Target
    } -ArgumentList $url | Out-Null
}

& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
