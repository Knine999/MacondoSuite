# Compilar los ejecutables de Macondo

Esta carpeta genera tres `.exe` independientes a partir del mismo código:

| Ejecutable | Qué hace |
|---|---|
| `MacondoLogger.exe` | Solo el **Bug Logger** (loguear bugs en JaaS con IA). |
| `MacondoWorkLogger.exe` | Solo el **WorkLogger** (registrar horas en JaaS). |
| `MacondoSuite.exe` | Los **dos**, en pestañas, con una sola conexión. |

Los tres comparten el mismo núcleo (`core.py`, `worklogger_core.py`), así que un
arreglo en la lógica sirve para todos.

---

## Requisitos (una vez por PC)

1. **Python 3.11 o superior** desde [python.org](https://www.python.org/downloads/).
   Al instalar, marca **"Add python.exe to PATH"**.
2. Nada más: los `.bat` instalan las dependencias solos.

> La compilación **solo funciona en Windows**. El `.exe` se genera en tu PC;
> desde aquí se entrega el código fuente y las instrucciones.

---

## Compilar

Doble clic sobre el `.bat` que necesites:

- **`build_all.bat`** → genera los tres `.exe`.
- `build_macondo.bat` → solo `MacondoLogger.exe`.
- `build_worklogger.bat` → solo `MacondoWorkLogger.exe`.
- `build_suite.bat` → solo `MacondoSuite.exe`.

Los ejecutables quedan en la carpeta **`dist\`**. Tarda unos minutos la primera vez.

Si prefieres la línea de comandos:

```cmd
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller MacondoSuite.spec --noconfirm
```

---

## Probar sin compilar (modo desarrollo)

Para ver la app antes de generar el `.exe`:

```cmd
python -m pip install -r requirements.txt
python -m streamlit run macondo_suite_app.py
```

(o `macondo_app.py` / `worklogger_app.py` para las versiones sueltas).

---

## Primer arranque de un `.exe`

1. Al abrirlo se levanta un servidor local y se abre el navegador solo.
2. **Bug Logger / Suite:** la primera vez pide la **Groq API Key** (se guarda
   cifrada en este equipo, no hay que pegarla de nuevo).
3. Pide el **JaaS PAT Token** una vez (también queda cifrado con el
   Administrador de credenciales de Windows).

---

## Si algo falla

- **"No encontré Python"** → instálalo marcando *Add to PATH* y reabre el `.bat`.
- **`pyinstaller` no reconocido** → usa `python -m PyInstaller ...` (los `.bat` ya lo hacen).
- **"No module named keyring" al abrir el `.exe`** → borra la carpeta `build\` y
  recompila; el `.spec` ya incluye keyring y su backend de Windows.
- **Windows SmartScreen / Defender bloquea el `.exe`** → es normal en un `.exe`
  sin firma digital. *Más información → Ejecutar de todas formas*. Para
  distribución amplia conviene firmarlo (ver la ficha de distribución).
