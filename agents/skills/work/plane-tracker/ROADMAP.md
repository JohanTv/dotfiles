# Propuestas pendientes de plane-tracker

Este documento recoge lo acordado que **todavía no existe en el código**. Nada de lo que figura aquí está disponible; no lo cites como si lo estuviera.

## Verificar que Plane devuelve `external_id` en los GET de comentarios

La cola de salida envía `external_id` en cada comentario y, antes de reenviar uno ambiguo, lo busca por su `client_id` en el HTML del comentario y por igualdad de `external_id`. La búsqueda en el HTML no depende de que Plane devuelva `external_id`; la igualdad sí. Falta confirmar en un Plane real que:

- el POST de comentarios acepta `external_source` y `external_id`;
- un POST repetido con el mismo par responde 409 con el `id` del comentario existente;
- los GET de comentarios devuelven `external_id`;
- la paginación de comentarios (`cursor`, `next_cursor`, `next_page_results`) tiene la misma forma que la de los tickets.

## Gestión de worktrees multi-repo por ticket

Analizado el 2026-10-31; no implementado. Detalle completo en [`issues/0002-worktrees-multi-repo-por-ticket.md`](./issues/0002-worktrees-multi-repo-por-ticket.md).

- **Decisión:** script `bin/work/plane-worktree` de ~70 líneas, fuera del CLI (el comando no necesita ningún dato de Plane y hereda su gate de credenciales).
- **Se activa cuando:** se cree un segundo worktree multi-repo a mano, o se reescriba el layout dos veces.

## Standby externo sin fuente de datos

Detectado el 2026-10-31 y pendiente de evaluar a fondo; no implementado. Detalle en [`issues/0003-standby-externo-sin-fuente-de-datos.md`](./issues/0003-standby-externo-sin-fuente-de-datos.md).

- **Hecho:** el reporte siempre lista `stoppers`, pero ningún flag ni código los alimenta, y sin datos imprime "0h 00m (Sin bloqueos reportados)".
- **Decisión pendiente:** quitar la línea o alimentarla (`--stopper`, o tiempo en `Pausado` desde las transiciones).
