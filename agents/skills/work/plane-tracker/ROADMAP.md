# Propuestas pendientes de plane-tracker

Este documento recoge lo acordado que **todavía no existe en el código**. Nada de lo que figura aquí está disponible; no lo cites como si lo estuviera.

## Verificar que Plane devuelve `external_id` en los GET de comentarios

La cola de salida envía `external_id` en cada comentario y, antes de reenviar uno ambiguo, lo busca por su `client_id` en el HTML del comentario y por igualdad de `external_id`. La búsqueda en el HTML no depende de que Plane devuelva `external_id`; la igualdad sí. Falta confirmar en un Plane real que:

- el POST de comentarios acepta `external_source` y `external_id`;
- un POST repetido con el mismo par responde 409 con el `id` del comentario existente;
- los GET de comentarios devuelven `external_id`;
- la paginación de comentarios (`cursor`, `next_cursor`, `next_page_results`) tiene la misma forma que la de los tickets.
