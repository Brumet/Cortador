@echo off
title Cortador - by Brumet
cd /d "%~dp0"

rem Primera vez: crea el entorno e instala todo. Despues solo arranca.
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  ========================================
  echo   Instalando Cortador por primera vez
  echo   Esto tarda un par de minutos.
  echo  ========================================
  echo.
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  No he encontrado Python. Instalalo desde https://www.python.org/downloads/
    echo  y marca la casilla "Add Python to PATH".
    echo.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e ".[web,app]"
)

echo.
echo  Abriendo Cortador... (cierra esta ventana para salir)
echo.
".venv\Scripts\python.exe" -m cortador.cli app
pause
