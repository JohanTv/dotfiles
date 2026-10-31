# 0003 · El "Standby externo" del reporte no tiene fuente de datos

- **Estado:** propuesta para evaluar de forma exhaustiva; sin implementar
- **Detectado:** 2026-10-31, al acortar la bitácora de cierre (la plantilla larga traía `is_blocked` y `blocker_details`, que nadie lee)
- **Tipo:** defecto latente de datos + decisión de producto pendiente
- **Área:** `comment add` / `comment edit` (flag nuevo), reporte diario (`timeutil.py`, `cmd_report.py`)

## Contexto

El reporte diario y el semanal muestran una línea de bloqueos externos. La fuente es la columna `stoppers_json` del worklog, que sale del campo `stoppers` de la metadata del comentario. Al acortar la bitácora (`SKILL.md` §4) se quitó el JSON escrito por el agente, y con él la única vía por la que un `stoppers` podía llegar al reporte. Se descartó añadir `--stopper` en ese cambio porque la fuente ya estaba muerta antes y el alcance era otro; queda aquí para decidir con más información.

## Evidencia verificada

| Hecho | Ubicación | Consecuencia |
| :--- | :--- | :--- |
| El reporte diario imprime `⏸️ Standby externo: ...` con la unión de `stoppers` de las filas | `scripts/plane_cli/timeutil.py:185-211` | Es el único consumidor diario. |
| Sin bloqueos imprime `Standby externo: 0h 00m (Sin bloqueos reportados)` | `timeutil.py:213` | El reporte afirma "sin bloqueos" aunque nadie pueda reportarlos: dato engañoso, no neutro. |
| El reporte semanal imprime `⏸️ STANDBY TOTAL` desde `stoppers_json` | `scripts/plane_cli/cmd_report.py:177-216` | Segundo consumidor. |
| `comment add` fija `stoppers: []` al generar la metadata y lo copia a la fila | `cmd_comment.py:187,220` | Ningún flag lo alimenta. |
| `comment edit` también fija `stoppers: []` al vincular un comentario sin telemetría | `cmd_comment_ops.py:149` | Mismo hueco en la edición. |
| `sync` solo recupera `stoppers` si el comentario ya lo traía en su bloque oculto | `scripts/plane_cli/sync.py:135` | Los comentarios nuevos no lo traen. |
| La plantilla anterior escribía `is_blocked` y `blocker_details`, no `stoppers` | `SKILL.md` (versión anterior de §4) | Nada convertía esas claves: el standby ya no se alimentaba antes del cambio. |
| El estado `Pausado` se excluye del cycle time activo | `scripts/plane_cli/flow.py:152` | Existe un segundo canal real de "bloqueado", sin cantidad de tiempo asociada. |

## Preguntas que la evaluación debe cerrar

1. **¿Se quiere este dato?** Si el reporte para jefatura no lo usa, lo correcto es quitar la línea y no construir el flag. Si se usa, ¿con qué decisión se acompaña?
2. **¿Texto o tiempo?** Hoy la línea lista textos, pero se rotula "0h 00m", lo que sugiere minutos de bloqueo. ¿Se necesita una duración (`--blocked-minutes`) o basta la razón?
3. **¿`Pausado` ya cubre el caso?** Comparar los dos canales (estado del ticket frente a campo del worklog) y decidir cuál es la fuente de verdad. `report flow` ya mide tiempo por estado, así que el tiempo en `Pausado` podría salir de las transiciones sin pedirle nada al agente (por verificar).
4. **Forma del flag, si se construye:** `--stopper "texto"` repetible en `comment add` y en `comment edit`, con tope de longitud y de cantidad, y sin romper el límite de 700 caracteres de la bitácora.
5. **Interacción con el rechazo por longitud:** el texto del stopper vive en la metadata, no en el cuerpo visible; confirmar que no cuenta para el límite.
6. **Histórico:** los comentarios antiguos con `blocker_details` no se migran; decidir si se ignora o se hace un barrido único con `report --refresh`.
7. **Otros agentes:** agy y opencode leen la misma skill; el flag nuevo debe documentarse en una sola línea de `SKILL.md` §4, sin volver a inflarla.

## Criterio de cierre

- Decisión registrada: quitar la línea del reporte, o alimentarla por una vía verificable.
- Si se alimenta: golden tests de `comment add --stopper` y de `report --today` con y sin bloqueos, y la línea "Sin bloqueos reportados" deja de aparecer cuando la fuente no existe.
- Si se quita: el reporte no afirma "0h 00m" y los golden `report*.txt` se actualizan.
