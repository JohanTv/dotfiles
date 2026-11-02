---
id: "0017"
title: La sincronización de worklogs depende de una lista fija de proyectos y de una lectura de comentarios por ticket
status: corregido
created: 2026-11-01
summary: "`sync` consulta solo proyectos fijados en el código, lee los comentarios ticket por ticket y no pagina de forma efectiva (`limit` lo ignora la API), así que un periodo con muchos tickets o fuera de esos proyectos produce un reporte parcial presentado como completo."
---

# 0017 · La sincronización de worklogs depende de una lista fija de proyectos y de una lectura de comentarios por ticket

- **Área:** `scripts/plane_cli/worklog_sync.py` (antes `sync.py`) (consulta de tickets y de comentarios), `report`.
- **Relacionado:** [0010](./0010-reporte-no-sincroniza-periodos-con-registros-parciales.md), [0009](./0009-saneamiento-pendiente-de-datos-de-instancia.md) (la lista fija), [0022](./0022-sync-presenta-valores-por-defecto-como-medidos.md), RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) (prerrequisito de `report time`) y [`hechos-de-la-api.md`](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/hechos-de-la-api.md).

## Diagnóstico corregido

La primera versión de este documento afirmaba que `limit=15` truncaba la sincronización. **Es falso:** la API **ignora `limit`** y devuelve la página completa por defecto (1000 filas; el parámetro que pagina es `per_page`). La causa real es otra:

1. **Lista fija de proyectos** en el código (`sync.py`): lo que está fuera de esa lista no se sincroniza nunca, y un identificador de proyecto desconocido no da error (la lista de destino queda vacía).
2. **Una lectura de comentarios por ticket** (N+1) y sin paginar: con la API devolviendo 1000 por página es aceptable en tamaño, pero cada ticket cuesta una petición y el límite de tasa es de unas 60 por ventana.
3. **Marca de sincronización global** (`sync:{workspace}`), no por proyecto ni por periodo (ver 0010).
4. El reporte presenta como completo un resultado que no se verificó.

## Síntoma

Un periodo con más tickets de los que caben en el presupuesto de peticiones, o con tickets de proyectos fuera de la lista, devuelve un reporte parcial sin aviso (P5).

## Solución propuesta

1. Sincronizar los proyectos **accesibles** (`is_member`, no archivados), no una lista fija.
2. Usar `per_page` y `cursor` explícitos y `order_by=-updated_at` con corte local por la fecha del periodo; los filtros de servidor por fecha **no funcionan**.
3. Acotar las lecturas de comentarios a los tickets con actividad en el periodo y respetar el límite de tasa (cabeceras `X-RateLimit-*`), deteniéndose con cobertura parcial.
4. Marca de sincronización por proyecto y periodo, y nota de cobertura cuando algo quedó fuera.
5. Partir `sync_remote_worklogs` (149 de 150 líneas) antes de cambiarla.

## Corrección (fase 4 del RFC 0021)

`sync.py` se partió en funciones pequeñas y ahora: sincroniza los proyectos **accesibles** (un `-p` desconocido o sin acceso es `unknown_project`, ya no una lista vacía en silencio); pagina con `per_page=100` y `cursor` ordenando por `-updated_at` y se detiene al llegar a una página toda anterior al periodo (la API ignora `limit` y los filtros de fecha); lee los comentarios solo de los tickets con actividad en el periodo; se detiene antes de agotar el presupuesto de tasa (`X-RateLimit-Remaining`) y deja la sincronización marcada como incompleta; y escribe una marca **por proyecto y periodo** (`worklog_sync`). Un fallo de lectura de comentarios (404, 403, 500) también deja ese proyecto incompleto en vez de ignorarse. La lectura de comentarios es **incremental por ticket** (`worklog_issue_sync`: un ticket cuyo `updated_at` no cambió no se relee; `report --refresh` relee todo), de modo que una sincronización cortada por el presupuesto de tasa avanza en la siguiente y **converge**: verificado contra una Plane real (solo lectura) con un periodo pasado y tres proyectos accesibles, que quedó completo en 3 ejecuciones sin ninguna respuesta 429. Las pruebas están en `tests/test_worklog_sync.py`, contra un servidor falso que ignora `limit` y pagina: 22 tickets con registros y un proyecto fuera de la antigua lista fija se reconstruyen completos.

## Criterio de cierre

- Un periodo con más de 15 tickets con registros, y tickets de un proyecto que no estaba en la lista fija, se reconstruyen completos (golden contra un servidor falso que **ignora `limit`** como la API real).
- Un periodo ya pasado se reconstruye completo.
- Si el presupuesto de tasa no alcanza, el reporte lo dice en `coverage`/`notes`.
