# Plan de migración

Parte de [0021](./README.md). Seis fases; cada una es entregable por sí sola y **deja la suite verde**. Los golden se regeneran con `GOLDEN_UPDATE=1` y **se revisan a mano** (el diff debe ser solo lo esperado de la fase). Cada fase termina con commits atómicos en inglés y el estado del documento actualizado.

Orden de dependencias: 0 → 1 → 2 → 3 → 4 → 5. La fase 2 es la que rompe a los agentes ya cargados, por eso incluye el cambio de regla externa ([`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md)).

## Fase 0 · Contrato y vigilancia (sin cambio de comportamiento)

- **Entrega:** decisión que fija el contrato (`docs/decisions/`, tras la revisión de este RFC), `vocabulary.py`, `errors.py`, `coverage.py`, `envelope.py` (con `validate`), y `tests/test_architecture.py` con F1-F13 **escritas**: las que dependen de fases posteriores quedan saltadas con motivo y su fase las activa.
- **Archivos:** módulos nuevos de capa 1 y 3; `test_architecture.py`; enmienda de `ARCHITECTURE.md` (capas y nomenclatura).
- **Golden:** ninguno cambia.
- **Aceptación:** `test_docs`, `test_structure` y F3/F4/F8 (unitarias) verdes; el vocabulario y [`contrato-json.md`](./contrato-json.md) coinciden (F4).
- **Riesgo:** diseñar el vocabulario sin usarlo. Mitigación: se valida contra los JSON reales de hoy (tabla "nombres que sustituye").

## Fase 1 · Alcance, almacenes y frescura

- **Entrega:** `scope.py`, `scope_flags.py`, `store_issues.py`, `store_worklogs.py`, `freshness.py`. `list` y los reportes empiezan a usar `resolve_scope` (validación única de proyecto, persona y periodo) sin cambiar aún sus formas de salida. `add_period_args` sube de `cmd_report` a `scope_flags`.
- **Golden:** cambia solo el error de proyecto desconocido en `report*`/`worklog check` (ahora validan con la misma pista).
- **Aceptación:** F2 activa para los comandos migrados; un solo lugar valida `-p`; `list_filtered.py` reducido a la lógica de `list`.
- **Riesgo:** regresiones de caché/TTL. Mitigación: los golden de offline y de sincronización existentes.

## Fase 2 · Una sola `list` (fusión de `search`) y sobre de lectura

- **Entrega:** vista `list` (`query_issues`, `render_issues`) sobre el sobre `plane-tracker/1`; `--text`, `--limit` único; se **borran** `cmd_search`, el camino API de `list`, `cached_issues`/`LIST_LIMIT` y el atajo numérico; `renamed.py` da pistas (`search` → `list --text`, texto posicional → `--text`). `get`, `labels` y `projects` adoptan el sobre.
- **Externo (misma entrega):** `rules/src/work.md` y la regeneración con `make work`; `SKILL.md`, `references/*`, `ARCHITECTURE.md`. Ver [`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md).
- **Golden:** `read_list_search_labels_projects`, `list_filters`, `get`, `errors_*`, `help`; `test_cli_tree` (TREE, LEAF_ARGS) y `test_offline_reads`, `test_renamed`.
- **Aceptación:** F3, F5, F6, F7, F9, F12 activas y verdes; `grep -rn "plane-tracker search"` vacío salvo la pista de `renamed`; el presupuesto de ayuda se mantiene.
- **Riesgo:** el churn de golden oculta una regresión. Mitigación: revisar cada diff contra el vocabulario y mantener el comportamiento de `search` cubierto por casos de `list --text` equivalentes (tokenización, fallback LIKE, `rank`).

## Fase 3 · `report` como grupo (`time`, `flow`) con resumen y periodo común

- **Entrega:** `report time` (la vista implícita de hoy) y `report flow` como vistas; `--from/--to/--week` en lugar de `--today/--date`; `summary` en JSON (horas por día, por proyecto y por balde de capacidad; la unión de intervalos hoy solo en texto); cobertura de horas en `coverage` (`hours_local_only`, `hours_unsigned`, `pending_unpublished`); `worklog check` adopta el alcance y el sobre.
- **Golden:** `report*`, `report_flow`, `worklog_check`, `help`.
- **Aceptación:** F10, F11 activas; `report` sin vista termina con código 2 y pista; el filtro de proyecto es el mismo en las tres.
- **Riesgo:** los reportes dependen de defectos abiertos ([0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md), [0017](../../defects/0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md)). Mitigación: el sobre los declara en `notes` en vez de esconderlos; corregirlos es trabajo aparte y aterriza mejor tras esta fase.

## Fase 4 · `report agenda` ([0005](../0005-vista-personal-agenda-y-backlog/README.md), fase 1)

- **Entrega:** la vista de carga, vencidos, estancados y trabajo invisible sobre el mismo almacén y selección que `list --mine --open`; incluye `target_date` y `plane_updated_at`.
- **Aceptación:** `agenda` no duplica lógica de `list` (comparten `query_issues`); F10 completa.
- **Riesgo:** definir "estancado" y "vencido" sin base. Mitigación: umbrales explícitos y declarados en `scope`/`summary`, sin puntajes (tensión Goodhart de `principles.md`).

## Fase 5 · `sync`, errores y escrituras

- **Entrega:** `sync [--history] [--budget N]` (sale de `list`); contrato de errores en todos los comandos (`CliError`, sobre de error en `--json`); escrituras con el sobre de resultado (`status`, `action`, `ticket`, `uuid`); `whoami --json`.
- **Golden:** todos los que imprimen errores o resultados de escritura (con revisión manual).
- **Aceptación:** ningún `sys.exit(1)` fuera de `errors`/`cli`; el contrato de [`contrato-json.md`](./contrato-json.md) se declara **estable** y la evolución pasa a ser aditiva.
- **Riesgo:** fase ancha. Mitigación: se puede partir por familia de comandos, cada una con su golden.

## Seguimiento

| Fase | Estado | Decisión o commit |
| :--- | :--- | :--- |
| 0 | pendiente | |
| 1 | pendiente | |
| 2 | pendiente | |
| 3 | pendiente | |
| 4 | pendiente | |
| 5 | pendiente | |

Este RFC pasa a `implementado` solo cuando las seis fases estén cerradas; hasta entonces ningún documento cita el modelo como existente.
