@echo off
rem Pobieranie faktur zakupowych z KSeF. Uruchom dwuklikiem.
chcp 65001 >nul
title Faktury z KSeF
cd /d "%~dp0"

set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"

"%UV%" run --frozen --quiet ksef pobierz --otworz
if errorlevel 1 (
    echo.
    echo Cos poszlo nie tak. Zrob zdjecie tego okna i wyslij je osobie, ktora instalowala program.
    echo Nacisnij dowolny klawisz, aby zamknac.
    pause >nul
    exit /b 1
)

echo.
echo Gotowe. Okno zamknie sie samo.
timeout /t 5 >nul
