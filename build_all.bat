@echo off
REM Compila los TRES ejecutables de una vez. Doble clic sobre este archivo.
REM Resultado: dist\MacondoLogger.exe, dist\MacondoWorkLogger.exe, dist\MacondoSuite.exe
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo No encontre Python. Instala Python 3.11+ desde python.org marcando "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [1/5] Instalando dependencias...
%PY% -m pip install --upgrade -r requirements.txt pyinstaller || goto :error

echo [2/5] Limpiando compilaciones anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/5] Compilando MacondoLogger.exe...
%PY% -m PyInstaller MacondoLogger.spec --noconfirm || goto :error
if exist build rmdir /s /q build

echo [4/5] Compilando MacondoWorkLogger.exe...
%PY% -m PyInstaller MacondoWorkLogger.spec --noconfirm || goto :error
if exist build rmdir /s /q build

echo [5/5] Compilando MacondoSuite.exe...
%PY% -m PyInstaller MacondoSuite.spec --noconfirm || goto :error

echo.
echo Listo. En la carpeta dist\ tienes:
echo   - MacondoLogger.exe       (solo Bug Logger)
echo   - MacondoWorkLogger.exe   (solo registro de horas)
echo   - MacondoSuite.exe        (los dos, en pestanas)
pause
exit /b 0

:error
echo.
echo La compilacion fallo. Copia el texto de arriba para revisarlo.
pause
exit /b 1
