---
id: "0023"
title: Una lectura que recibe un 403 termina el programa en vez de degradar
status: abierto
created: 2026-11-02
summary: "`fail_http` hace `sys.exit(1)` ante cualquier 4xx definitivo, así que `list --all-projects` (y cualquier lectura multi-proyecto) aborta entera si un proyecto no es accesible para el usuario."
---

# 0023 · Una lectura que recibe un 403 termina el programa en vez de degradar

- **Área:** `scripts/plane_cli/api.py` (`fail_http`), `cache.sync_issues_cache`, `resolve.get_states_map`/`get_labels_map`, `list`, `search`, reportes.
- **Relacionado:** RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) (fase 1) y [`hechos-de-la-api.md`](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/hechos-de-la-api.md).

## Síntoma (reproducido con la API real, solo lectura)

En un workspace con un proyecto en el que el usuario **no es miembro** (`is_member: false`), `GET issues/`, `states/` y `labels/` de ese proyecto responden **403**. `list --all-projects` con caché fría hizo 15 GET en 13,9 s y terminó con **código 1 y salida vacía**: el 403 de un solo proyecto abortó la lectura de todos. Además, el listado de proyectos incluye proyectos archivados.

## Causa verificada

`api_request` trata los 4xx como errores definitivos: imprime y llama a `sys.exit(1)` (`fail_http`), salvo con `raise_on_error=True`. Los lectores de caché (`sync_issues_cache`, `get_states_map`, `get_labels_map`) no usan `raise_on_error`, así que un 403 no es capturable por quien llama y el programa termina. Tampoco se filtran los proyectos por `is_member` ni `archived_at`.

## Comportamiento esperado

Una lectura multi-proyecto omite los proyectos sin acceso o archivados, los declara en la cobertura (`unavailable` y la nota `source_forbidden`) y devuelve el resto.

## Solución propuesta

1. Filtrar el alcance a los proyectos accesibles y no archivados (`GET projects/`).
2. Los lectores de red usan `raise_on_error` y traducen un 403 inesperado a cobertura (la membresía puede cambiar), nunca a `sys.exit`.
3. Golden con un proyecto `is_member: false` y otro archivado.

## Criterio de cierre

- `list --all-projects` sobre un workspace con un proyecto sin acceso devuelve los demás y lo declara en `coverage.unavailable`; el código de salida es 0.
