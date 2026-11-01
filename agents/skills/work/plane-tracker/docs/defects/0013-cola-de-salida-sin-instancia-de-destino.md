---
id: "0013"
title: La cola de salida no registra a qué instancia pertenece cada comentario
status: abierto
created: 2026-11-01
summary: "`outbox flush` publica con las credenciales del entorno actual; con dos instancias y una sola base local, un comentario podría publicarse en la instancia equivocada."
---

# 0013 · La cola de salida no registra a qué instancia pertenece cada comentario

- **Área:** cola de salida (`scripts/plane_cli/outbox.py`, `outbox_flush.py`, tabla `outbox` en `db.py`), configuración (`config.py`, `cli.py`).
- **Relacionado:** [RFC 0014](../rfcs/0014-contextos-y-perfiles-personal-y-trabajo/README.md) (contextos y perfiles), [0009](./0009-saneamiento-pendiente-de-datos-de-instancia.md).

## Síntoma (riesgo, no observado todavía)

Con una sola instancia no ocurre nada. Si una misma máquina y una misma base local (`~/.cache/plane`) se usan contra **dos instancias** (por ejemplo, una de trabajo y otra personal), un comentario encolado para una puede publicarse en la otra: lo que se encola es un texto con una referencia de ticket, y el destino lo decide el entorno de quien ejecuta la publicación.

## Causa verificada

- La tabla `outbox` guarda `ticket_ref`, `payload_json` y la clave del worklog (`wl_*`), pero **no** la URL base ni el workspace de destino.
- `flush_items(conn, base_url, api_key, workspace, ...)` recibe las credenciales del entorno actual y resuelve cada `ticket_ref` contra esa instancia (`outbox_flush.py:28-51,80`). Si existe el mismo prefijo de ticket en la instancia equivocada, el comentario se publica ahí.
- La base es única: `CACHE_DIR = ~/.cache/plane` se fija al importar (`config.py:13`) y ninguna variable la cambia; solo `HOME` la mueve.
- Las credenciales que falten del entorno se completan desde `~/.zshrc.local` (`config.py:54-79`) sin avisar de qué instancia se está usando.
- `payload_json` guarda el texto de los comentarios en claro (directorio 0700, base 0600): es el canal de fuga principal de una herramienta que publica comentarios.

## Comportamiento esperado

Un comentario encolado solo puede publicarse en la instancia para la que se creó. Ante cualquier duda, la herramienta se niega a publicar (falla cerrado).

## Solución propuesta

1. Guardar en cada fila de `outbox` una huella de destino (`base_url` y `workspace`) y, en la base, una tabla de metadatos con la huella de la instancia con la que se creó.
2. `outbox flush` rechaza cualquier fila cuya huella no coincida con el entorno actual, con un mensaje que indique cuál es la instancia esperada.
3. Con más de un perfil y un contexto ambiguo, las escrituras se rechazan (ver el RFC 0014).
4. Pruebas de aislamiento: dos servidores falsos; con la instancia A activa, la B no debe recibir ninguna petición, tampoco desde `outbox flush`. Y una prueba "canario": un título único no debe aparecer en ninguna petición dirigida a la otra instancia.

## Criterio de cierre

- Las pruebas de aislamiento de arriba pasan.
- Una fila antigua sin huella se trata de forma explícita (se pide confirmación o se descarta), nunca se publica a ciegas.
