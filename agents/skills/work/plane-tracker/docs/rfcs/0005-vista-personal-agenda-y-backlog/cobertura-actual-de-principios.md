# Cobertura actual de los principios (instantánea del 2026-10-31)

Contexto para quien retome el [RFC 0005](./README.md): qué cubre hoy la herramienta de cada principio de [`principles.md`](../../principles.md) y qué falta. Se obtuvo leyendo el código y la documentación y ejecutando los comandos contra una instancia real. Cuando se implemente el RFC, esta instantánea se actualiza o se sustituye por una fecha posterior.

## Pregunta que lo originó

La herramienta no podía responder a "¿cuál es mi trabajo abierto, qué está vencido y qué dejé de lado, y por qué?". Casi todo el diseño gira en torno a otra pregunta: "¿qué horas registré?".

## Cobertura por principio

| Principio | Qué hay hoy | Qué falta | Dónde se resuelve |
| :--- | :--- | :--- | :--- |
| **P1 · Trabajo invisible** | Tickets paraguas semanales, regla de los 15 minutos y baldes de capacidad (`toil_support`, `coordination`), descritos en `references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md`. | No se captan interrupciones ni cambios de contexto: la medición solo cubre sesiones de agente (`scripts/session_clock.py`). El reporte agrupa por proyecto y no por balde, así que no compara contra la meta de cada balde. Un paraguas puede existir sin horas y nada lo señala. | RFC 0005 fases 1 (sección "trabajo invisible") y 3. |
| **P2 · Autonomía** | Local-first, cola de salida offline, nunca hay envío automático, la duración se propone y se confirma, nunca se estima, `session_clock` lee solo marcas de tiempo y no contenido. | El formato del reporte lo dicta el destinatario. No existe una vista personal ni separación entre lo que se ve y lo que se envía. | RFC 0005 fase 4. |
| **P3 · Datos para quien trabaja** | `focus status`, `report flow` (lead time, cycle time, tiempo por estado) y `health`. | Nada responde "¿qué tengo abierto?". `issues_cache` no guarda asignados ni creador (`scripts/plane_cli/db.py`), `create` y `update` no los aceptan y `list` no filtra por persona, estado ni proyecto. El JSON crudo de la API sí trae `assignees` y `created_by`. | RFC 0005 fases 0 y 1. |
| **P4 · Carga cognitiva** | Estados del ticket y bitácora de cierre de 700 caracteres como máximo. | No hay conteo de trabajo en curso, ni antigüedad, ni "sin movimiento hace N días", ni un límite sugerido de trabajo en curso. | RFC 0005 fase 1 (sección "carga"). |
| **P5 · Expectativas** | Existen `target_date`, prioridad y métricas de flujo. | Ningún comando evalúa los vencimientos, así que un compromiso vence en silencio. No se distingue compromiso de intención. No hay pronóstico a partir de la mediana de cycle time ni comparación entre lo comprometido al inicio de la semana y lo cerrado. | RFC 0005 fases 1 y 3. |

## Afirmaciones sin fuente (P5, veracidad del reporte)

Dos casos en los que el reporte presenta como cierto algo que no se midió o no está completo:

1. **Standby externo:** imprime "0h 00m (Sin bloqueos reportados)" aunque ningún flujo puede reportar bloqueos. Ver el defecto [0003](../../defects/0003-standby-externo-sin-fuente-de-datos.md) y la decisión pendiente en el RFC [0006](../0006-standby-externo-fuente-de-datos.md).
2. **Periodo con registros parciales:** el reporte semanal no sincroniza con Plane si ya hay algún registro local en el periodo, y muestra como completo un resultado parcial. Ver el defecto [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md).

## El backlog

- Ningún informe lo toca: `report` solo lee `worklogs`.
- No existe un registro de **por qué** se difiere algo importante (motivo, costo de no hacerlo, quién decidió, fecha de revisión). Una decisión consciente de priorizar otra cosa queda sin rastro y, con el tiempo, se confunde con un olvido.
- Propuesta: registro de diferimiento (RFC 0005 fase 2), con el mismo mecanismo de bloque oculto que ya usa el worklog.

## Principios técnicos relacionados

- **Ley de Little:** el tiempo medio de entrega crece con el trabajo en curso; limitar lo que está abierto a la vez acorta cada ítem. Sustenta P4 y la sección "carga" de `agenda`. Ver [`principles.md`](../../principles.md).
- **Una sola fuente de verdad por dato:** el estado de un ticket vive en Plane. La caché local lo refleja y debe avisar cuando no está al día (defecto 0010).
- **No afirmar lo que no se midió:** si no hay fuente, el reporte lo dice o calla (defecto 0003).
