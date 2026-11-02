---
id: "0016"
title: El bloque oculto de telemetría se escapa y queda visible al publicar o editar comentarios
status: corregido
created: 2026-11-01
summary: "`markdown_to_html` escapa `<!-- PLANE_WORKLOG_METADATA ... -->`; `comment edit -m` pierde la telemetría y `comment add -m` publica el bloque visible además del real."
---

# 0016 · El bloque oculto de telemetría se escapa y queda visible al publicar o editar comentarios

- **Área:** `comment add` / `comment edit` (`scripts/plane_cli/cmd_comment.py`, `cmd_comment_ops.py`), `mdhtml.py`.
- **Origen:** segundo defecto descrito dentro de [0001](./0001-registro-retroactivo-de-horas.md); aquí se separa porque ocurre hoy y no depende de la solución de las ventanas de tiempo.

## Síntoma observado

Reproducido con `markdown_to_html('Hola\n<!-- PLANE_WORKLOG_METADATA {...} -->')`: devuelve `<p>Hola<br>&lt;!-- PLANE_WORKLOG_METADATA ... --&gt;</p>`. El bloque pasa de comentario HTML oculto a texto visible.

- **`comment edit -m`:** la cadena `PLANE_WORKLOG_METADATA` sigue presente tras el escape, así que `cmd_comment_ops.py:109` cree que ya hay bloque y no conserva el original. El comentario queda con el bloque visible y sin telemetría (`worklog check` avisa `[no_block]`).
- **`comment add -m "texto + bloque"`:** `cmd_comment.py:156-159` publica el bloque escapado y visible además del real.
- **Prueba que lo congela:** `tests/golden/comment.txt:152` registra el HTML escapado como comportamiento esperado.

## Comportamiento esperado

El bloque oculto nunca se escapa: se detecta en el texto original (antes de `markdown_to_html`) y se conserva o se inserta tal cual, sin duplicarse.

## Solución propuesta

1. Extraer el bloque del texto antes de convertirlo y reinsertarlo después, en `add` y en `edit`.
2. Detectar "ya hay bloque" sobre el bloque real, no sobre la cadena suelta.
3. Regenerar a propósito el golden `comment.txt` y añadir uno de `edit -m` que conserve la telemetría.

## Criterio de cierre

- `comment edit -m "<texto nuevo>"` deja el comentario sin bloque visible y con su telemetría original.
- `comment add -m "<texto + bloque>"` publica un único bloque, oculto.
- `worklog check` queda limpio tras ambos flujos.
