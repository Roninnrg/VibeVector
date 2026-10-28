@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ===================================
echo   УСТАНОВКА ПРОЕКТА "ВЕКТОР"
echo ===================================
echo.
echo [ИНФО] Эта установка займет 10-20 минут
echo [ИНФО] Будет скачано ~1.5 ГБ (модели + ffmpeg)
echo.
pause

REM Проверка Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Python не найден!
    echo Скачайте Python с https://www.python.org/downloads/
    echo При установке обязательно отметьте "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/6] Создание виртуального окружения...
if exist ".venv" (
    echo [ИНФО] Удаляем старое окружение...
    rmdir /s /q ".venv"
)
python -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось создать .venv
    pause
    exit /b 1
)

echo [2/6] Обновление pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1

echo [3/6] Установка зависимостей...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)

echo [4/6] Установка ffmpeg...
".venv\Scripts\python.exe" scripts\setup_tools.py
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось установить ffmpeg
    pause
    exit /b 1
)

echo [5/6] Скачивание моделей (Whisper + эмбеддинги)...
".venv\Scripts\python.exe" scripts\download_models.py
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось скачать модели
    pause
    exit /b 1
)

echo [6/6] Загрузка демо-лекций...
if not exist "data\vector.db" (
    ".venv\Scripts\python.exe" scripts\seed_demo.py
) else (
    echo [ИНФО] База уже есть, пропускаем
)

echo.
echo ===================================
echo   УСТАНОВКА ЗАВЕРШЕНА!
echo ===================================
echo.
echo Теперь можно запускать проект через START.bat
echo.
pause
