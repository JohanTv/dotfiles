---
id: "0018"
title: Eliminar tickets sin destruir horas por accidente
status: aceptado
created: 2026-11-01
summary: "`delete` decide leyendo en vivo todos los comentarios del ticket unidos a lo local, falla cerrado y rechaza siempre las horas ajenas; conservar con Cancelado es la vía por defecto."
---

# 0018 · Eliminar tickets sin destruir horas por accidente

Relacionado: [principles.md](../principles.md) (P1, P2, P5), defectos [0010](../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) y [0017](../defects/0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md), RFC [0011](../rfcs/0011-cache-compartida-entre-maquinas/README.md).

## Contexto

Los worklogs no son una entidad de Plane: se publican como comentarios del ticket con un bloque oculto. Eliminar el ticket destruye esas horas en Plane sin remedio, y la base local es solo una caché que la sincronización nunca depura.

## Decisión

- **La fuente es Plane, en vivo, para ese ticket.** No se sincroniza antes: la sincronización depende de los defectos 0010 y 0017, es global y deja una ventana. Se leen todos los comentarios con cursor; una lectura fallida o incompleta aborta (nunca se asume "sin horas").
- **Local ∪ remoto.** Cuenta como horas todo comentario con el bloque oculto (aunque esté dañado o escapado) o con la tabla heredada, más las filas locales sin comentario en Plane.
- **Fallar cerrado.** Sin horas: `--yes`. Horas propias: además `--discard-worklogs`. Horas de otros o de autor no confirmado (sin `PLANE_USERNAME` ni `PLANE_ACTOR_UUID`): se rechaza siempre.
- **La vía por defecto es conservar:** `update T --state Cancelado` mantiene el ticket y sus horas. `delete` queda para tickets creados de más y sin horas.
- **Orden:** leer y decidir, eliminar en Plane y limpiar lo local. Si el ticket ya no existe (se perdió la respuesta de un intento anterior), limpia lo local y termina con éxito.
- El ticket se indica completo (`PREFIJO-N` o UUID): nunca se deduce de la rama de Git.

## Descartado

- **Exigir `report --refresh` antes:** frágil por 0010 y 0017, masivo para un ticket y solo trae comentarios propios.
- **Que `delete` sea un alias de Cancelado:** pierde la posibilidad de retirar de verdad un ticket sin horas.

## Consecuencias

- Las otras máquinas conservan filas locales huérfanas y las seguirán contando: la sincronización no borra y `worklog check` no las marca. Pendiente: podarlas en `--refresh` (ver 0011).
- Adjuntos, enlaces, subtareas e historial no se consultan; el aviso lo dice. Un ticket completado que se elimina sale de las medianas de cycle time (P5).
- Entre la lectura y el borrado un comentario nuevo se perdería; se acepta.
- Por verificar con una instancia real: que el borrado de un ticket responda 204 y cómo pagina Plane los comentarios.
