@echo off
REM Compila SOLO Macondo Suite (Bug Logger + WorkLogger en pestanas). Doble clic sobre este archivo.
REM Resultado: dist\MacondoSuite.exe
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo No encontre Python. Instala Python 3.11+ desde python.org marcando "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
%PY% -m pip install --upgrade -r requirements.txt pyinstaller || goto :error

echo [2/3] Limpiando compilacion anterior...
if exist build rmdir /s /q build

echo [3/3] Compilando MacondoSuite.exe (tarda unos minutos)...
%PY% -m PyInstaller MacondoSuite.spec --noconfirm || goto :error

echo.
echo Listo: dist\MacondoSuite.exe
pause
exit /b 0

:error
echo.
echo La compilacion fallo. Copia el texto de arriba para revisarlo.
pause
exit /b 1
