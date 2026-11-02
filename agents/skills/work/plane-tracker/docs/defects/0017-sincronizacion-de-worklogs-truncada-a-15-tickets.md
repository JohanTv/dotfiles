---
id: "0017"
title: La sincronización de worklogs consulta solo los 15 tickets más recientes por proyecto
status: abierto
created: 2026-11-01
summary: "`sync` pide `limit=15` sin paginar; un periodo con más tickets tocados, o uno ya pasado, produce un reporte parcial presentado como completo."
---

# 0017 · La sincronización de worklogs consulta solo los 15 tickets más recientes por proyecto

- **Área:** `scripts/plane_cli/sync.py` (consulta de tickets por proyecto), `report`.
- **Relacionado:** [0010](./0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) (no se puede cerrar sin este), [0009](./0009-saneamiento-pendiente-de-datos-de-instancia.md) (la lista fija de proyectos del mismo bloque).

## Síntoma (verificado en código, no observado en una instancia)

`sync.py:51` pide `?order_by=-updated_at&limit=15` por proyecto y no pagina. Los worklogs se reconstruyen desde los comentarios de esos tickets, así que:

- Un periodo con más de 15 tickets tocados pierde los demás.
- Un periodo pasado puede quedar fuera de los 15 más recientes por `updated_at`.
- El reporte no avisa de nada: presenta el resultado como completo (P5).

Por verificar con una instancia real: que Plane respete `limit` y cómo pagina.

## Comportamiento esperado

La sincronización de un periodo recorre todos los tickets con actividad en él, o avisa de que el resultado es parcial.

## Solución propuesta

1. Paginar con cursor, como ya hace `sync_issues_cache` (`cache.py:58`, `limit=100`).
2. Acotar por fechas del periodo en lugar de "los últimos N".
3. Si no se puede completar, el reporte lo dice en su primera línea.

## Criterio de cierre

- Con más de 15 tickets con registros en el periodo, `report --week --refresh` los incluye todos (golden contra servidor falso paginado).
- Un periodo ya pasado se reconstruye completo.
- El criterio de cierre del 0010 se cumple sin `--refresh`.
