---
id: "0004"
title: Verificar que Plane devuelve `external_id` en los GET de comentarios
status: abierto
created: 2026-10-31
summary: La cola de salida asume un contrato de `external_id` de Plane que no se ha confirmado en una instancia real.
---

# 0004 · Verificar que Plane devuelve `external_id` en los GET de comentarios

- **Tipo de ítem:** verificación pendiente de un supuesto (riesgo latente, no un defecto observado).
- **Área:** cola de salida (`outbox.py`, `outbox_flush.py`) y `sync.py`.

## Contexto

La cola de salida envía `external_id` en cada comentario y, antes de reenviar uno ambiguo, lo busca por su `client_id` en el HTML del comentario y por igualdad de `external_id`. La búsqueda en el HTML no depende de que Plane devuelva `external_id`; la igualdad sí.

## Qué falta confirmar en una instancia real

- El POST de comentarios acepta `external_source` y `external_id`.
- Un POST repetido con el mismo par responde 409 con el `id` del comentario existente.
- Los GET de comentarios devuelven `external_id`.
- La paginación de comentarios (`cursor`, `next_cursor`, `next_page_results`) tiene la misma forma que la de los tickets.

## Criterio de cierre

Las cuatro comprobaciones se ejecutan contra una instancia real y se registra el resultado aquí. Si alguna falla, se abre un defecto con el comportamiento observado.
