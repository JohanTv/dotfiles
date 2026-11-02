---
id: "0020"
title: Las etiquetas de la caché de tickets se guardan siempre vacías
status: abierto
created: 2026-11-02
summary: "`sync_issues_cache` inserta `labels_csv` como cadena vacía, así que la búsqueda por etiqueta no funciona y un filtro futuro por etiqueta tampoco."
---

# 0020 · Las etiquetas de la caché de tickets se guardan siempre vacías

- **Área:** `scripts/plane_cli/cache.py` (`sync_issues_cache`), búsqueda `search` (índice FTS).

## Síntoma observado

`issues_cache.labels_csv` y la columna `labels_csv` del índice FTS son siempre `''`: el `INSERT` de `cache.py` lo fija así. La búsqueda `search` solo encuentra por título y cualquier filtro por etiqueta no podría funcionar.

## Causa verificada

El payload de `/issues/` trae `labels` como lista de UUID; el nombre vive en otro endpoint (`/labels/`), cacheado por `get_labels_map` en `resolve.py`. `cache.py` no lo consulta (y `resolve.py` importa `cache.py`, así que hay un ciclo de importación que resolver).

## Comportamiento esperado

`labels_csv` lleva los nombres de las etiquetas del ticket y `search` los usa.

## Solución propuesta

1. Resolver los UUID a nombres con las etiquetas ya cacheadas del proyecto (sin petición extra si el TTL no venció), rompiendo el ciclo de importación (función auxiliar en un módulo neutro o importación diferida).
2. Regenerar los golden de `search` y de las sincronizaciones, que añadirán la petición a `/labels/`.

## Criterio de cierre

- `search "<nombre de etiqueta>"` encuentra tickets etiquetados; golden con etiquetas en los fixtures.
