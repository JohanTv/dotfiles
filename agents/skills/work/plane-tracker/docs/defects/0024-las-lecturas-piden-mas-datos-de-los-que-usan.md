---
id: "0024"
title: Las lecturas piden más datos de los que usan
status: abierto
created: 2026-11-02
summary: "`list` baja hasta 1000 tickets con su descripción para imprimir 15, `resolve_issue` recorre el listado paginado del proyecto para encontrar un ticket y `limit` no limita nada porque la API lo ignora."
---

# 0024 · Las lecturas piden más datos de los que usan

- **Área:** `cmd_read.py` (`list`), `resolve.resolve_issue`, `cache._fetch_all_issues`, `api` (cabeceras de tasa).
- **Relacionado:** RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) y [`hechos-de-la-api.md`](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/hechos-de-la-api.md).

## Síntomas (verificados)

- **`limit` no limita:** la API ignora `limit`; el parámetro real es `per_page` (por defecto 1000). `list` pide `?limit=50` y recibe todo el proyecto (unos 487 KB y 3 a 6 s para 217 tickets, porque cada ticket trae su `description_html`) para imprimir 15.
- **`resolve_issue` recorre el listado** paginado del proyecto buscando el `sequence_id`, cuando existe `GET workspaces/{ws}/issues/{PRJ}-{n}/` (1 GET). Lo usan `get`, `report flow`, `worklog check`, `update` y otros.
- **La caché descarga la descripción** de todos los tickets aunque nunca la usa (`fields=` la omite).
- **Las cabeceras de tasa se descartan** (`X-RateLimit-Remaining`/`Reset`): con unas 60 peticiones por ventana, una lectura en frío cuesta `3N + 1` GET y puede agotar la cuota sin que nadie lo sepa.

## Solución propuesta

1. `per_page=100` explícito y `fields=` sin descripción en la sincronización de tickets.
2. Resolver el ticket por su identificador (1 GET) y usar el listado solo como respaldo.
3. Exponer las cabeceras de tasa en `api.py` y detenerse con cobertura parcial antes de agotar la cuota.
4. Dejar de pasar `limit` (no tiene efecto).

## Criterio de cierre

- `get` de un ticket cuesta 1 GET para resolverlo; la sincronización de un proyecto descarga mucho menos que hoy (medido con un servidor falso que ignora `limit` y respeta `fields`).
