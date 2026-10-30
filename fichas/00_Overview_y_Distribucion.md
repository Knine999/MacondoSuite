# Macondo Suite — Overview, distribución y mantenimiento

## Qué es

Dos herramientas de QA que hablan con JaaS (Jira EA), con la misma identidad visual
(🦋 mostaza). Se distribuyen en tres ejecutables según lo que necesite cada persona:

| Ejecutable | Contiene | Para quién |
|---|---|---|
| `MacondoLogger.exe` | Bug Logger con IA | Testers que solo loguean bugs |
| `MacondoWorkLogger.exe` | Registro de horas | Quien solo imputa tiempo |
| `MacondoSuite.exe` | Ambos, en pestañas | El día a día de un tester de skate |

Todo corre **en local**: cada `.exe` levanta un servidor en `localhost` y abre el
navegador. No hay backend ni datos en la nube de la herramienta.

## Impacto de negocio (resumen)

- **Bug Logger:** convierte una nota suelta en un ticket completo y bien estructurado
  en segundos. Menos tiempo por bug, formato consistente entre testers, y una curva
  de aprendizaje más corta para gente nueva. Escala a otras franquicias sin reescribir
  nada: cada proyecto aprende su propio estilo.
- **WorkLogger:** elimina el imputar hora por hora, ticket por ticket, a mano en JaaS.
  Registra un periodo completo (varios días, varias actividades) en una sola pasada,
  con los IDs de ticket traídos frescos por API.

*(El impacto por proyecto está en cada ficha: SK8, PL1, FCQV, F1.)*

## Arquitectura (por qué un solo código)

```
core.py              ← núcleo compartido: JaaS, Groq, ML, credenciales (Bug Logger)
worklogger_core.py   ← lógica del registro de horas (usa core para la conexión)
macondo_theme.py     ← la paleta mostaza, en un solo lugar
macondo_login.py     ← pantalla de conexión reutilizable
bug_logger_ui.py     ← pantalla del Bug Logger  (render)
worklogger_ui.py     ← pantalla del WorkLogger  (render)
macondo_app.py / worklogger_app.py / macondo_suite_app.py  ← las tres apps
```

Un arreglo en la lógica (ej. un cambio en cómo responde JaaS) se hace **una vez** en
el núcleo y sirve para los tres ejecutables.

## Autenticación hoy y mañana

- **Hoy:** cada persona usa su **JaaS PAT Token**, que se guarda **cifrado** en el
  Administrador de credenciales de Windows (keyring), por usuario de Windows. Los
  proyectos que ve cada quien salen de sus **permisos reales** en JaaS, filtrados por
  su cuenta (correo EA). Nadie ve ni usa el token de otro.
- **Mañana (recomendado):** login con **usuario de EA vía SSO/OAuth**. Requiere que
  JaaS/EA registre la app como cliente OAuth. Mientras eso no exista, el PAT + keyring
  es la opción viable y segura. El código ya aísla la conexión en `core.py` y
  `macondo_login.py`, así que migrar a OAuth es cambiar solo esa capa.

## Seguridad

- Tokens y Groq key: **cifrados** en keyring, nunca en texto plano en disco.
- **Pendiente crítico:** el PAT que apareció en texto en un archivo subido debe
  considerarse comprometido — **rótalo en JaaS**.
- La Groq key solo genera texto (no identifica a nadie), pero igual va cifrada y no
  debe pegarse en chats.

## Distribución

1. Compilar en una PC Windows con `build_all.bat` (ver `BUILD_EXE.md`).
2. Repartir el/los `.exe` por el canal interno (carpeta de red, Teams, etc.).
3. **Primer arranque:** SmartScreen/Defender puede avisar porque el `.exe` no está
   firmado → *Más información → Ejecutar de todas formas*.
   - Para reparto amplio conviene **firmar el `.exe`** con un certificado de EA
     (elimina el aviso). Es el paso recomendado antes de pasar de un piloto al equipo
     completo.
4. Cada PC configura una vez su Groq key (Bug Logger) y su JaaS token.

## Mantenimiento (general)

| Cada cuánto | Qué revisar |
|---|---|
| Cuando Groq cambie de modelo | `GROQ_MODEL` en `core.py` (hoy `openai/gpt-oss-120b`). |
| Si JaaS cambia campos de un proyecto | Nada en código: la app lee los campos por API. Solo revisar si aparece un tipo de campo nuevo que la UI no sabe dibujar. |
| Por versión nueva de skate | Nada: el WorkLogger trae las versiones frescas por API. |
| Rotación de tokens | Según política de EA; el PAT se vuelve a pegar una vez. |
| Dependencias | `requirements.txt` sin versiones fijadas; si algo se rompe, fijar la versión que funcionaba. |

El detalle de mantenimiento **por proyecto** está en cada ficha.
