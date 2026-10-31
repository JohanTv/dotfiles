# 0001 · No se puede fijar inicio y fin reales al registrar tiempo declarado

- **Estado:** abierto
- **Detectado:** 2026-10-30, al validar los worklogs del día
- **Área:** `comment add` / `comment edit` / `worklog check` (`scripts/plane_cli/cmd_comment.py`, `cmd_comment_ops.py`, `worklog.py`)

## Contexto
`plane-tracker comment add --duration N` registra un worklog "declarado" (sin sesión medida). Al registrar tiempo de forma retroactiva (una reunión que terminó horas antes, trabajo de la mañana publicado por la tarde) la herramienta no permite indicar cuándo ocurrió: usa la hora de publicación como fin y resta la duración para calcular el inicio.

## Síntoma observado
Horas registradas frente a las reales (la duración era correcta en todas):

| Ticket | Real | Registrado |
| :--- | :--- | :--- |
| OPS-17, reunión con RR. HH. | 10:05–10:45 | 10:08–10:48 |
| OPS-17, reunión con Preventas | 11:05–12:10 | 11:07–12:12 |
| OPS-17, reunión con Omar | 14:40–18:20 | **16:27–20:07** (publicada a las 20:07) |
| OMNIFY-208 y OMNIFY-235 (25 min cada uno) | sin hora exacta | ambos 19:39–20:04 (misma ventana) |

La fusión de intervalos solapó la reunión de Omar con 208 y 235 y contó una sola vez los dos intervalos idénticos: `report --today` mostró 5 h 25 min de reloj activa frente a 6 h 15 min de esfuerzo, y el "AI Leverage Multiplier" (1,15x) salió distorsionado. `worklog check` marcó 0 inconsistencias porque solo compara comentarios con worklogs, no las horas.

## Comportamiento esperado
Poder registrar el tiempo con su ventana real (fecha, inicio y fin) cuando se declara de forma retroactiva, o al menos corregirla después, sin duplicar ni depender de la hora de publicación.

## Causa verificada
- `_record_measurement` (`cmd_comment.py`): con una propuesta medida (`--accept-proposal`) guarda `start_time`/`end_time` de la sesión; con duración declarada solo anota `measured_by: declared` y el worklog usa la hora de publicación como fin (lo dice la ayuda de `comment edit --duration`).
- `worklog propose` tiene `--date`, `--since` y `--until`, pero `comment add` y `comment edit` no los ofrecen para duraciones declaradas.
- `comment edit --duration` corrige con `corrected_metadata`, que solo cambia duración, track, capacidad y tipo de ejecutor; nunca inicio ni fin.
- **Segundo defecto (encontrado al intentar el workaround):** `comment edit -m "<texto + <!-- PLANE_WORKLOG_METADATA ... -->>"` pasa el texto por `markdown_to_html`, que escapa el bloque (`&lt;!-- ...`). Como la cadena `PLANE_WORKLOG_METADATA` sigue presente en el HTML, la comprobación de `cmd_comment_ops.py` (~líneas 107-117) cree que ya hay bloque y no conserva el original: el comentario queda con el bloque **visible como texto** y sin telemetría (`worklog check` avisa `[no_block]`).
- `ROADMAP.md` documenta el modo offline y la bandeja de salida, pero no el registro retroactivo de horas.

## Workaround usado (2026-10-30)
Script de un solo uso que importa `plane_cli` y, por comentario: lee el worklog local, cambia `start_time`/`end_time` (validando que la ventana coincida con la duración), reemplaza el bloque con `replace_metadata_block` (o reconstruye el primer párrafo visible si el comentario quedó dañado), hace `PATCH` de `comment_html` y reinserta el worklog local (`DELETE` por `plane_comment_id` + `upsert_worklog`). Tras `report --refresh` las horas persisten (reconstruidas desde los comentarios) y `worklog check` queda limpio.

## Solución propuesta
1. Añadir `--date`, `--since` y `--until` a `comment add` y `comment edit` para worklogs declarados: validar `since < until`, que la ventana coincida con `--duration` (o derivarla si se omite) y que no sea futura.
2. Advertir si la ventana se solapa con otros worklogs del mismo ejecutor humano (la fusión de intervalos oculta el solape).
3. Permitir corregir un worklog existente sin publicar otro (`comment edit --since/--until`) y hacer que `worklog check` compare también las horas del comentario con las del worklog local.
4. Corregir el defecto de `comment edit -m`: detectar el bloque oculto en el texto original (antes de `markdown_to_html`) y conservarlo o insertarlo sin escapar.
5. Documentar el caso retroactivo en `SKILL.md` y en `rules/src/work.md`, con tests de regresión (golden).

## Criterios de aceptación
- Registrar una reunión de 14:40 a 18:20 publicada a las 20:07 guarda `14:40`–`18:20` y el reporte no la solapa con otros tickets.
- Corregir un worklog existente sin crear comentarios nuevos y sin dejar el bloque visible.
- `worklog check` avisa cuando la hora del worklog difiere de la declarada en el comentario.
- Tests y documentación actualizados.
