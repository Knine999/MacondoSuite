# Ficha de proyecto — F1 (Formula 1, onboarding futuro)

> Ficha de ejemplo para cuando **otra franquicia** adopte Macondo. F1 es solo el caso
> ilustrativo; aplica igual a cualquier equipo nuevo.

## Qué cambia al sumar una franquicia nueva
**Casi nada**, y ese es el punto. La herramienta es multi-proyecto por diseño:

1. El tester de F1 abre el mismo `MacondoLogger.exe` (o la Suite).
2. Se conecta con **su** token de JaaS.
3. En la lista de proyectos aparece **F1** porque la app lee sus **permisos reales**;
   elige F1 y listo.
4. Los campos de F1 se leen por API (los de F1, no los de skate).

No hay que compilar una versión "de F1" ni tocar código.

## Impacto de negocio
- Demuestra que la inversión escala: un mismo ejecutable sirve a varias franquicias,
  con el costo marginal casi en cero por equipo nuevo.
- Estándar de calidad de bugs **común entre equipos**, manteniendo el estilo propio de
  cada juego.

## Cómo aprende (ML) desde cero
- F1 arranca **sin ejemplos propios**: la app usa un estilo base neutral mientras tanto.
- A medida que el tester de F1 corrige summaries/descriptions, F1 acumula **su propio**
  archivo de ejemplos (`buglogger_examples_F1.json`), independiente del de skate.
- En pocas semanas, la IA escribe con el estilo de F1.

## Mantenimiento
- Nada específico de código. Solo asegurarse de que el equipo de F1 tenga permisos
  **Create Issue** en su proyecto.
- Si F1 usa un registro de horas con la misma convención `Time Tracking`, el WorkLogger
  les sirve cambiando solo la clave del proyecto en la pantalla.

## Checklist para onboarding de una franquicia nueva
- [ ] El equipo tiene proyecto en JaaS y permisos de creación.
- [ ] Repartir el `.exe` (o apuntar a la carpeta de red donde está).
- [ ] Cada PC: Groq key una vez + token de JaaS.
- [ ] Primer bug de prueba en su proyecto (o en PL1) para validar el flujo.
- [ ] (Opcional) Ajustar la clave del proyecto de horas si usan WorkLogger.
