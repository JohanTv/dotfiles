---
id: "0022"
title: La sincronización presenta valores por defecto como si estuvieran medidos
status: abierto
created: 2026-11-02
summary: "`sync` rellena balde, fase, rol y horas con valores por defecto cuando el comentario no los trae, y la caché no distingue lo medido de lo supuesto; los estados desconocidos caen en 'Pendiente'."
---

# 0022 · La sincronización presenta valores por defecto como si estuvieran medidos

- **Área:** `scripts/plane_cli/sync.py` (construcción de la fila de `worklogs`), `worklog.upsert_worklog`, `cache.sync_issues_cache`.
- **Relacionado:** principio "no afirmar lo que no se midió" ([`principles.md`](../principles.md)), [0017](./0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md), RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) (prerrequisito de `report time`).

## Síntoma (verificado en el código)

Al reconstruir un worklog desde un comentario cuya telemetría es parcial, `sync` completa lo que falta con valores inventados y los guarda igual que los medidos:

- `capacity_bucket` → `deep_work`, `phase` → `dev`, `role` → `backend_engineer`, `worker_type` → `human`, `track` → `main`.
- `date`, `start_time` y `end_time` → derivados de la hora actual y de la duración (el instante de la sincronización, no el del trabajo).
- Estado desconocido de un ticket (`cache.sync_issues_cache`) → `("Pendiente", "unstarted")`.

Consecuencias: un reporte agrupado por balde de capacidad atribuye a `deep_work` horas cuyo balde nunca se declaró; las fechas dependen de cuándo se sincronizó (la sincronización deja de ser determinista); y un ticket en un estado que la caché no conoce parece pendiente.

## Comportamiento esperado

Lo que no viene en el comentario queda **marcado como no medido**: no se inventa un balde ni una hora, o se guarda con su procedencia (`measured` frente a `default`) para que los reportes lo excluyan o lo etiqueten.

## Solución propuesta

1. Registrar la procedencia por campo (columna o marca en la fila) y poner `default` cuando el valor no vino del comentario.
2. Que los reportes agrupen lo no medido aparte (balde "sin declarar") y avisen con la nota `hours_defaulted`, en vez de sumarlo a `deep_work`.
3. No derivar fecha ni hora de `clock` al sincronizar: si el comentario no las trae, la fila no entra en reportes por periodo y se cuenta como no medida.
4. Estado desconocido: mostrarlo como tal (`state: "unknown"`), no como "Pendiente".

## Criterio de cierre

- Un comentario con telemetría parcial no produce una fila con horas o balde inventados; el golden de sincronización lo muestra.
- Dos sincronizaciones del mismo comentario en instantes distintos producen filas idénticas.
- Un reporte por balde separa lo no declarado de `deep_work`.
