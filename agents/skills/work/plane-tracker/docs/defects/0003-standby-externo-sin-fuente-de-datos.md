---
id: "0003"
title: El "Standby externo" del reporte no tiene fuente de datos
status: abierto
created: 2026-10-31
summary: El reporte afirma "Sin bloqueos reportados" aunque ningún flujo puede reportar bloqueos; la decisión de producto está en 0006.
---

# 0003 · El "Standby externo" del reporte no tiene fuente de datos

- **Detectado:** al acortar la bitácora de cierre (la plantilla larga traía `is_blocked` y `blocker_details`, que nadie lee).
- **Área:** `comment add` / `comment edit`, reporte diario y semanal (`timeutil.py`, `cmd_report.py`).
- **Decisión de producto relacionada:** [0006](../rfcs/0006-standby-externo-fuente-de-datos.md).

## Contexto

El reporte diario y el semanal muestran una línea de bloqueos externos. La fuente es la columna `stoppers_json` del worklog, que sale del campo `stoppers` de la metadata del comentario. Al acortar la bitácora (`SKILL.md` §4) se quitó el JSON escrito por el agente, y con él la única vía por la que un `stoppers` podía llegar al reporte. La fuente ya estaba muerta antes de ese cambio.

## Síntoma observado

Sin bloqueos, el reporte imprime `Standby externo: 0h 00m (Sin bloqueos reportados)`. Es una afirmación que nadie puede desmentir porque nadie puede reportar bloqueos: un dato engañoso, no neutro.

## Evidencia verificada

| Hecho | Ubicación | Consecuencia |
| :--- | :--- | :--- |
| El reporte diario imprime `⏸️ Standby externo: ...` con la unión de `stoppers` de las filas | `scripts/plane_cli/timeutil.py:185-211` | Es el único consumidor diario. |
| Sin bloqueos imprime `Standby externo: 0h 00m (Sin bloqueos reportados)` | `timeutil.py:213` | El reporte afirma "sin bloqueos" aunque nadie pueda reportarlos. |
| El reporte semanal imprime `⏸️ STANDBY TOTAL` desde `stoppers_json` | `scripts/plane_cli/cmd_report.py:177-216` | Segundo consumidor. |
| `comment add` fija `stoppers: []` al generar la metadata y lo copia a la fila | `cmd_comment.py:187,220` | Ningún flag lo alimenta. |
| `comment edit` también fija `stoppers: []` al vincular un comentario sin telemetría | `cmd_comment_ops.py:149` | Mismo hueco en la edición. |
| `sync` solo recupera `stoppers` si el comentario ya lo traía en su bloque oculto | `scripts/plane_cli/sync.py:135` | Los comentarios nuevos no lo traen. |
| La plantilla anterior escribía `is_blocked` y `blocker_details`, no `stoppers` | `SKILL.md` (versión anterior de §4) | Nada convertía esas claves. |
| El estado `Pausado` se excluye del cycle time activo | `scripts/plane_cli/flow.py:152` | Existe un segundo canal real de "bloqueado", sin cantidad de tiempo asociada. |

## Criterio de cierre

- El reporte deja de afirmar "0h 00m" o "Sin bloqueos reportados" mientras la fuente no exista.
- Los golden `report*.txt` se actualizan en consecuencia.
- Si [0006](../rfcs/0006-standby-externo-fuente-de-datos.md) se acepta y se implementa, el reporte vuelve a mostrar la línea alimentada por la vía verificable que ese RFC decida.
