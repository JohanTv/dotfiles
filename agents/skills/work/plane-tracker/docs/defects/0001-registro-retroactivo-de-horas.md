---
id: "0001"
title: No se puede fijar inicio y fin reales al registrar tiempo declarado
status: corregido
created: 2026-10-30
summary: "`comment add --duration` usa la hora de publicación como fin; el registro retroactivo distorsiona la fusión de intervalos."
---

# 0001 · No se puede fijar inicio y fin reales al registrar tiempo declarado

- **Detectado:** al validar los worklogs de un día.
- **Área:** `comment add` / `comment edit` / `worklog check` (`scripts/plane_cli/cmd_comment.py`, `cmd_comment_ops.py`, `worklog.py`)

## Contexto
`plane-tracker comment add --duration N` registra un worklog "declarado" (sin sesión medida). Al registrar tiempo de forma retroactiva (una reunión que terminó horas antes, trabajo de la mañana publicado por la tarde) la herramienta no permite indicar cuándo ocurrió: usa la hora de publicación como fin y resta la duración para calcular el inicio.

## Síntoma observado
Horas registradas frente a las reales (la duración era correcta en todas):

| Ticket (ejemplo) | Real | Registrado |
| :--- | :--- | :--- |
| Reunión corta de la mañana | 10:05–10:45 | 10:08–10:48 |
| Reunión de la mañana | 11:05–12:10 | 11:07–12:12 |
| Reunión larga de la tarde, publicada a las 20:07 | 14:40–18:20 | **16:27–20:07** |
| Dos tickets de 25 min cada uno, sin hora exacta | sin hora exacta | ambos 19:39–20:04 (misma ventana) |

La fusión de intervalos solapó la reunión larga con los dos tickets de 25 min y contó una sola vez los dos intervalos idénticos: `report --today` mostró 5 h 25 min de reloj activa frente a 6 h 15 min de esfuerzo, y el "AI Leverage Multiplier" (1,15x) salió distorsionado. `worklog check` marcó 0 inconsistencias porque solo compara comentarios con worklogs, no las horas.

## Comportamiento esperado
Poder registrar el tiempo con su ventana real (fecha, inicio y fin) cuando se declara de forma retroactiva, o al menos corregirla después, sin duplicar ni depender de la hora de publicación.

## Causa verificada
- `_record_measurement` (`cmd_comment.py`): con una propuesta medida (`--accept-proposal`) guarda `start_time`/`end_time` de la sesión; con duración declarada solo anota `measured_by: declared` y el worklog usa la hora de publicación como fin (lo dice la ayuda de `comment edit --duration`).
- `worklog propose` tiene `--date`, `--since` y `--until`, pero `comment add` y `comment edit` no los ofrecen para duraciones declaradas.
- `comment edit --duration` corrige con `corrected_metadata`, que solo cambia duración, track, capacidad y tipo de ejecutor; nunca inicio ni fin.
- **Segundo defecto (encontrado al intentar el workaround):** `comment edit -m "<texto + <!-- PLANE_WORKLOG_METADATA ... -->>"` pasa el texto por `markdown_to_html`, que escapa el bloque (`&lt;!-- ...`). Como la cadena `PLANE_WORKLOG_METADATA` sigue presente en el HTML, la comprobación de `cmd_comment_ops.py` (~líneas 107-117) cree que ya hay bloque y no conserva el original: el comentario queda con el bloque **visible como texto** y sin telemetría (`worklog check` avisa `[no_block]`).

## Workaround usado
Script de un solo uso que importa `plane_cli` y, por comentario: lee el worklog local, cambia `start_time`/`end_time` (validando que la ventana coincida con la duración), reemplaza el bloque con `replace_metadata_block` (o reconstruye el primer párrafo visible si el comentario quedó dañado), hace `PATCH` de `comment_html` y reinserta el worklog local (`DELETE` por `plane_comment_id` + `upsert_worklog`). Tras `report --refresh` las horas persisten (reconstruidas desde los comentarios) y `worklog check` queda limpio.

## Solución propuesta
1. Añadir `--date`, `--since` y `--until` a `comment add` y `comment edit` para worklogs declarados: validar `since < until`, que la ventana coincida con `--duration` (o derivarla si se omite) y que no sea futura.
2. Advertir si la ventana se solapa con otros worklogs del mismo ejecutor humano (la fusión de intervalos oculta el solape).
3. Permitir corregir un worklog existente sin publicar otro (`comment edit --since/--until`) y hacer que `worklog check` compare también las horas del comentario con las del worklog local.
4. ~~Corregir el escape del bloque oculto en `comment edit -m`~~: separado y corregido en [0016](./0016-bloque-oculto-escapado-al-publicar-y-editar-comentarios.md).
5. Documentar el caso retroactivo en `SKILL.md`, con tests de regresión (golden).

## Corrección (2026-11-02)

1. **Ventana explícita en `comment add` y `comment edit`:** `--since HH:MM` y `--until HH:MM` fijan inicio y fin. Con los dos extremos la ventana manda y la duración es su delta (si además se pasa `--duration`, debe coincidir); con uno solo se completa con `--duration` o con la duración ya registrada. `--date YYYY-MM-DD` lleva el trabajo a otro día (nunca futuro). La ventana no cruza la medianoche ni termina en el futuro: vive en `worklog.resolve_window` / `worklog.requested_date` y lee el reloj solo por `clock`.
2. **Corrección sin publicar otro comentario:** `comment edit --since/--until [--date]` parte del bloque existente, marca `measured_by.kind="corrected"` y actualiza bloque oculto y fila local a la vez (mismo camino que `--duration`).
3. **`worklog check` ya cubre el criterio:** `CHECK_FIELDS` compara `date`, `start_time`, `end_time` y `duration_minutes` entre el comentario y la fila local, así que una ventana mal registrada sale como `mismatch`.
4. **Pruebas:** `tests/test_window.py` (unidad, reloj congelado) y los golden `comment` y `comment_edit_delete`, que incluyen el caso del criterio (`--date 2026-10-30 --since 14:40 --until 18:20` → 220 min), la corrección de una ventana existente y los rechazos (intervalo contradictorio, un extremo sin duración, ventana futura, orden invertido).
5. **Documentación:** `SKILL.md` §3 y §4 (reglas 3 y 6), `references/GUIA_OPERATIVA_CLI_PLANE_TRACKER.md` §E y §C.3, `references/ARQUITECTURA_SISTEMA_TRACKING_Y_TELEMETRIA.md` y `references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md` §3.3.

**Fuera de este defecto:** el aviso de solape entre worklogs del mismo ejecutor (solución propuesta 2) no está implementado; el registro honesto de la ventana es lo que evita hoy los solapes artificiales.

## Criterios de aceptación
- Registrar una reunión de 14:40 a 18:20 publicada a las 20:07 guarda `14:40`–`18:20` y el reporte no la solapa con otros tickets.
- Corregir un worklog existente sin crear comentarios nuevos y sin dejar el bloque visible.
- `worklog check` avisa cuando la hora del worklog difiere de la declarada en el comentario.
- Tests y documentación actualizados.
