# Ficha de proyecto — SK8 (skate.)

## Qué es
El proyecto **real** del equipo de skate en JaaS. Es el proyecto donde se loguean los
bugs de verdad del juego. La herramienta que aplica aquí es el **Bug Logger**.

## Impacto de negocio
- Es el **caso de uso principal** de Macondo. Cada bug bien escrito y consistente
  ahorra idas y vueltas entre QA y desarrollo.
- El componente de IA aprende el **estilo propio de SK8** (summaries, estructura de
  repro steps, secciones del Note) a partir de los tickets reales del proyecto y de
  tus correcciones, así que la calidad sube con el uso.
- Baja la curva de entrada para testers nuevos del equipo: el formato correcto sale
  "de fábrica".

## Cómo aprende (ML)
1. **Tus correcciones** en SK8 (lo más fiel): cada vez que editas el summary o la
   description en el preview y envías, se guarda como ejemplo para SK8.
2. **Tickets reales recientes** de SK8 en JaaS (estructura de la franquicia).
3. Si no hubiera nada de lo anterior, un **estilo base** de skate como punto de partida.

Los ejemplos aprendidos se guardan en `%APPDATA%\MacondoLogger\buglogger_examples_SK8.json`
(sobreviven a actualizaciones del `.exe` y se pueden respaldar).

## Campos
Se leen **por API** desde la pantalla de creación de SK8 (Pillar, Game Spine, Platform,
Repro Rate, Player Impact, Severity, Player Path, Activity, Changelist, Branch, Bug Type,
y cualquier otro que el proyecto tenga habilitado). No hay nada "hardcodeado" por versión.

## Mantenimiento
- **Ojo al enviar:** es el proyecto real. La app muestra un aviso en el preview antes
  de confirmar en SK8.
- Si el equipo agrega un campo obligatorio nuevo, la app lo detecta y lo pide solo;
  solo habría que tocar código si fuera un tipo de campo que la UI aún no dibuja.
- Revisar de vez en cuando que el archivo de ejemplos no crezca con correcciones malas
  (si alguien "enseñó" un formato incorrecto, se puede borrar ese JSON y vuelve a
  aprender).

## Riesgos / notas
- Requiere que el tester tenga permiso **Create Issue** en SK8 (lo normal en el equipo).
- Los adjuntos (logs, video, screenshots) se suben al ticket ya creado.
