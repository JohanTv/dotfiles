# Propuestas pendientes de plane-tracker

Este documento recoge diseños acordados que **todavía no existen en el código**. Ningún comando de aquí está disponible; no los cites como si lo estuvieran.

## Modo sin conexión: fallo rápido, lectura desde caché y cola de salida

**Estado:** propuesta, no implementada. **Prioridad:** baja (se activa si las caídas de Plane se repiten).

### Problema

Comportamiento actual cuando la API de Plane no responde (observado en una caída real: el frontend contestaba HTTP 200, la API daba 502 y luego timeouts):

- Cada comando tarda unos 32 s en fallar: `api_request` usa timeout de 10 s, 3 intentos y 1 s de pausa entre ellos. Medido: `list` 34 s, `search` 33 s, `worklog check` 31 s.
- `search` intenta refrescar la caché de tickets antes de buscar (`sync_issues_cache`), así que falla aunque la caché local bastara.
- `comment add` publica primero (POST) y solo después inserta el worklog local. Si Plane falla, no queda registro del tiempo trabajado.
- Lo que sí se conserva: el tiempo medido se recalcula desde el transcript de la sesión con `worklog propose --date <día> --session <id>`.

### Diseño propuesto

1. **Fallo rápido (interruptor de circuito).** Con el historial de `requests.log`: si las últimas N llamadas fallaron hace menos de una ventana corta, el comando responde de inmediato `Plane no responde (desde HH:MM)` sin esperar los timeouts, y sondea de nuevo tras un enfriamiento. Se consideran transitorios los 502/503/504, los timeouts y las conexiones rechazadas; los errores 4xx no. N, la ventana y el enfriamiento quedan por definir.
2. **Lecturas desde caché.** `search`, `labels` y `projects` responden con lo local indicando su antigüedad (`caché de hace 40 min; Plane no responde`). `get` muestra los metadatos cacheados, sin descripción ni comentarios.
3. **Cola de salida (`outbox`) solo para `comment add`.** Si Plane no responde, el comentario (HTML con su bloque oculto), el ticket y el worklog se guardan en una tabla local y el comando informa `en cola`. El worklog entra en `worklogs` con el comentario pendiente, de modo que la resta de tiempo ya registrado (`session_coverage`) sigue evitando contarlo dos veces. `create` no se encola: el identificador del ticket lo asigna Plane y lo usan las ramas. Si `update` debe encolarse queda por decidir.
4. **Sincronización explícita.** Grupo `outbox` con `list`, `flush` y `drop`. Cuando hay pendientes, los comandos avisan por stderr (`2 pendientes; ejecuta plane-tracker outbox flush`). `flush` publica en orden de creación y conserva las fechas y horas reales dentro del bloque oculto, que es lo que usan los reportes. No hay envío automático.
5. **Idempotencia.** Cada comentario encolado lleva un `client_id` en su bloque oculto. Antes de reintentar un envío se consultan los comentarios del ticket buscando ese `client_id`: si ya existe (el POST llegó pero se perdió la respuesta), se marca como enviado y se enlaza su id en lugar de duplicarlo.

### Fuera de alcance

Sincronización bidireccional de ediciones y resolución de conflictos. Plane es la fuente de verdad y la caché local es derivada; el único dato irrecuperable es lo que se escribe mientras Plane está caído.

### Decisiones y riesgos abiertos

- Si `update` entra en la cola y cómo tratar un estado que cambió mientras tanto.
- Límite de ritmo de la API al reenviar en lote (se observaron unas 60 llamadas por ventana de aproximadamente un minuto).
- Un ticket borrado o movido mientras el comentario estaba en cola: `flush` debe informar el fallo sin perder el comentario.
- Caducidad de los pendientes y qué ocurre con los de días anteriores.
- La cola contiene texto de comentarios: archivo con permisos `0600`.

### Pruebas previstas

- Servidor falso que responde 502 y timeouts: el comando falla en menos de 2 s con el circuito abierto y las lecturas cacheadas indican su antigüedad.
- POST aceptado con la respuesta perdida: tras `flush` hay un solo comentario.
- Varios pendientes: se publican en orden y el worklog local queda enlazado al comentario.
- Un worklog en cola no se vuelve a proponer en `worklog propose` (cobertura intacta).
- `flush` con el ticket inexistente: falla ese elemento, conserva el resto y no pierde datos.
