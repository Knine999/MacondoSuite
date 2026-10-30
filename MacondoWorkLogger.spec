# -*- mode: python ; coding: utf-8 -*-
# Macondo WorkLogger (solo registro de horas).
# Build:  build_all.bat   (o: python -m PyInstaller MacondoWorkLogger.spec --noconfirm)
# Resultado: dist\MacondoWorkLogger.exe
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

APP_FILES = [
    "launcher_worklogger.py",
    "worklogger_app.py",
    "worklogger_ui.py",
    "worklogger_core.py",
    "core.py",
    "macondo_theme.py",
    "macondo_login.py",
    "_launcher_base.py",
    "macondo_logo.jpg",
]

datas = [(f, ".") for f in APP_FILES]
binaries = []
hiddenimports = [
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "groq", "requests", "keyring",
]

datas += collect_data_files("streamlit")
for pkg in ("streamlit", "groq", "requests", "keyring"):
    datas += copy_metadata(pkg)

# El WorkLogger no usa IA, pero core.py importa groq al cargarse, asi que el
# paquete tiene que estar igual (si no, falla el import de core).
for pkg in ("groq",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

for pkg in ("keyring", "jaraco.classes", "jaraco.functools", "jaraco.context", "win32ctypes"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("keyring.backends")

a = Analysis(
    ["launcher_worklogger.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="MacondoWorkLogger",
    console=False,
    upx=False,
)
