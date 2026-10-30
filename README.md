# 🦋 Macondo Suite

Herramientas de QA para JaaS (EA), con la misma identidad visual. Tres ejecutables
a partir del mismo código:

- **MacondoLogger.exe** — loguear bugs en JaaS con ayuda de IA.
- **MacondoWorkLogger.exe** — registrar horas en JaaS.
- **MacondoSuite.exe** — los dos, en pestañas.

## Por dónde empezar
- **Compilar los `.exe`:** ver [`BUILD_EXE.md`](BUILD_EXE.md).
- **Qué es cada cosa, impacto y distribución:** ver [`fichas/00_Overview_y_Distribucion.md`](fichas/00_Overview_y_Distribucion.md).
- **Fichas por proyecto:** `fichas/SK8.md`, `fichas/PL1.md`, `fichas/FCQV.md`, `fichas/F1_futuro.md`.

## Probar sin compilar
```cmd
python -m pip install -r requirements.txt
python -m streamlit run macondo_suite_app.py
```

## Mapa de archivos
| Archivo | Rol |
|---|---|
| `core.py` | Núcleo del Bug Logger + conexión/credenciales compartidas |
| `worklogger_core.py` | Lógica del WorkLogger |
| `macondo_theme.py` | Paleta y tema (un solo lugar) |
| `macondo_login.py` | Pantalla de conexión reutilizable |
| `bug_logger_ui.py` / `worklogger_ui.py` | Las dos pantallas (`render()`) |
| `macondo_app.py` / `worklogger_app.py` / `macondo_suite_app.py` | Las tres apps |
| `_launcher_base.py` + `launcher_*.py` | Arranque de los `.exe` |
| `*.spec` / `build_*.bat` | Empaquetado con PyInstaller |
| `test_suite.py` | Pruebas con simulación |

## Pendiente antes de distribuir
- **Rotar el PAT de JaaS** que se expuso en texto plano.
- Validar un ticket real en **PL1** (bug con adjunto) desde el `.exe` compilado.
- (Opcional, para reparto amplio) **firmar** los `.exe` para evitar el aviso de SmartScreen.
