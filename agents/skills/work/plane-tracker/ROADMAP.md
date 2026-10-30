# Propuestas pendientes de plane-tracker

Este documento recoge lo acordado que **todavía no existe en el código**. Nada de lo que figura aquí está disponible; no lo cites como si lo estuviera.

## Idempotencia de `create` con `external_id`

**Estado:** propuesta, no implementada; requiere confirmación y una verificación en un Plane real. **Prioridad:** baja.

`create` no se encola: el identificador del ticket lo asigna Plane y lo usan las ramas, así que sin red falla con código 3. Un `create` cuya respuesta se pierde puede dejar un ticket duplicado al reintentarlo. La mitigación prevista es enviar `external_source` y `external_id` (un identificador determinista derivado del título, el proyecto y la fecha) y tratar un 409 con el `id` del ticket existente como éxito.

Antes de implementarla hay que comprobar con un POST de prueba en un ticket paraguas de `OPS`:

- que el endpoint de creación de work items acepta `external_id` y `external_source`;
- que un segundo POST con el mismo par responde 409 e incluye el `id` del ticket existente.

## Verificar que Plane devuelve `external_id` en los GET de comentarios

La cola de salida envía `external_id` en cada comentario y, antes de reenviar uno ambiguo, lo busca por su `client_id` en el HTML del comentario y por igualdad de `external_id`. La búsqueda en el HTML no depende de que Plane devuelva `external_id`; la igualdad sí. Falta confirmar en un Plane real que:

- el POST de comentarios acepta `external_source` y `external_id`;
- un POST repetido con el mismo par responde 409 con el `id` del comentario existente;
- los GET de comentarios devuelven `external_id`;
- la paginación de comentarios (`cursor`, `next_cursor`, `next_page_results`) tiene la misma forma que la de los tickets.
