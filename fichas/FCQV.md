# Ficha de proyecto — FCQV (registro de horas)

## Qué es
El proyecto en JaaS donde el equipo de skate **imputa el tiempo**. La herramienta que
aplica aquí es el **WorkLogger** (no el Bug Logger). El registro se organiza en tickets
de "Time Tracking".

## Cómo está organizado en JaaS
- Un ticket **"padre" por versión**, con un summary tipo `Time Tracking 0.31.5`
  (sin corchetes).
- Debajo, un ticket **"hijo" por actividad**, con el summary entre corchetes, tipo
  `[QA][Time Tracking] Regression - San Van`.
- El WorkLogger lee todo esto **por API**, detecta las versiones y saca las actividades
  de la versión que elijas. Siempre trae lo actual: no hay listas fijas en el código.

## Impacto de negocio
- Quita el trabajo manual de abrir cada ticket e imputar hora por hora. Se registra un
  **periodo completo** (varios días × varias actividades) en una sola pantalla.
- Menos errores de imputación y de días saltados; marca cuándo un día llega a las 8h.
- Cierre de semana/periodo mucho más rápido.

## Mantenimiento
- **Convención de nombres:** el WorkLogger depende de que los padres digan
  `Time Tracking <versión>` sin corchetes y los hijos lleven corchetes. Si el equipo
  cambia esa convención, hay que ajustar el patrón en `worklogger_core.py`
  (`find_available_versions` / `_clean_activity_label`).
- **Otros equipos:** el proyecto es configurable en la propia app (campo "Proyecto de
  registro de tiempo", por defecto FCQV). Un equipo nuevo con la misma convención solo
  cambia la clave del proyecto; no se toca código.
- La hora de inicio de cada worklog se fija a las 09:00 del día (JaaS exige una). Si se
  necesitara otra, está en `submit_worklog`.

## Riesgos / notas
- Requiere que el token tenga permiso para registrar tiempo en FCQV.
- El comentario de cada worklog es el **nombre de la actividad** (coincide con el
  ticket), para que quede trazable.
