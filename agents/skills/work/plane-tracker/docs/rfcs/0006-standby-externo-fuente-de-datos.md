---
id: "0006"
title: Decidir la fuente de datos del "Standby externo"
status: borrador
created: 2026-10-31
summary: Quitar la línea de bloqueos del reporte o alimentarla (flag, o tiempo en Pausado desde las transiciones).
---

# 0006 · Decidir la fuente de datos del "Standby externo"

- **Defecto relacionado:** [0003](../defects/0003-standby-externo-sin-fuente-de-datos.md) (el reporte afirma "sin bloqueos" sin fuente).
- **Área:** `comment add` / `comment edit` (flag nuevo), reporte diario y semanal.

## Contexto

Es la parte de decisión de producto que se separó del defecto 0003. El defecto se corrige con independencia de lo que aquí se decida.

## Preguntas que la evaluación debe cerrar

1. **¿Se quiere este dato?** Si el reporte hacia jefatura no lo usa, lo correcto es quitar la línea y no construir el flag. Si se usa, ¿con qué decisión se acompaña?
2. **¿Texto o tiempo?** Hoy la línea lista textos, pero se rotula "0h 00m", lo que sugiere minutos de bloqueo. ¿Se necesita una duración (`--blocked-minutes`) o basta la razón?
3. **¿`Pausado` ya cubre el caso?** Comparar los dos canales (estado del ticket frente a campo del worklog) y decidir cuál es la fuente de verdad. `report flow` ya mide tiempo por estado, así que el tiempo en `Pausado` podría salir de las transiciones sin pedirle nada al agente (por verificar).
4. **Forma del flag, si se construye:** `--stopper "texto"` repetible en `comment add` y en `comment edit`, con tope de longitud y de cantidad, y sin romper el límite de 700 caracteres de la bitácora.
5. **Interacción con el rechazo por longitud:** el texto del stopper vive en la metadata, no en el cuerpo visible; confirmar que no cuenta para el límite.
6. **Histórico:** los comentarios antiguos con `blocker_details` no se migran; decidir si se ignora o se hace un barrido único con `report --refresh`.
7. **Otros agentes:** otros asistentes leen la misma skill; el flag nuevo debe documentarse en una sola línea de `SKILL.md` §4, sin volver a inflarla.

## Criterio de cierre

- Decisión registrada: quitar la línea del reporte, o alimentarla por una vía verificable.
- Si se alimenta: golden tests de `comment add --stopper` y de `report --today` con y sin bloqueos.
- Si se quita: el reporte no afirma "0h 00m" y los golden `report*.txt` se actualizan.
