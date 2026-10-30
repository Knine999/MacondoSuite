@echo off
REM Corre Macondo Suite (Bug Logger + WorkLogger en pestañas) SIN compilar. Doble clic.
REM Se abre en el navegador. Para cerrarlo, cierra esta ventana negra.
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo No encontre Python. Instala Python 3.11+ desde python.org marcando "Add python.exe to PATH".
    pause
    exit /b 1
)

echo Instalando dependencias (solo la primera vez tarda)...
%PY% -m pip install -r requirements.txt

echo Abriendo Macondo Suite en el navegador...
%PY% -m streamlit run macondo_suite_app.py
pause
