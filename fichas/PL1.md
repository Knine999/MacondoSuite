# Ficha de proyecto — PL1 (PlaygroundBugLogger)

## Qué es
Proyecto **de pruebas** propio (Playground), donde tú sí tienes permiso de crear
tickets. Sirve para **probar la herramienta sin ensuciar SK8**.

## Impacto de negocio
- Es la **red de seguridad** de la distribución: antes de usar el Bug Logger contra
  el proyecto real, se valida aquí el flujo completo (login → campos → IA → envío →
  adjuntos) sin riesgo.
- Permite enseñar la herramienta a gente nueva y hacer demos sin crear ruido en el
  backlog real.

## Cómo aprende (ML)
Igual que cualquier proyecto: guarda sus propios ejemplos en
`%APPDATA%\MacondoLogger\buglogger_examples_PL1.json`. Como es de pruebas, su estilo
aprendido **no** afecta al de SK8 (cada proyecto aprende por separado).

## Mantenimiento
- Mantenerlo vivo mientras la herramienta siga evolucionando: es donde se prueba cada
  cambio antes de soltarlo al equipo.
- Si se llena de tickets de prueba, se pueden cerrar/borrar sin consecuencias.
- Cuando quieras validar "de punta a punta" una versión nueva del `.exe`: crear aquí
  un bug con adjunto y confirmar que llega bien a JaaS.

## Uso recomendado en la distribución
Primera prueba de cada PC nueva: conectar, abrir PL1, loguear un bug de prueba con un
screenshot. Si eso funciona, SK8 también funcionará.
