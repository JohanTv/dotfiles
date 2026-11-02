# Plan de implementación

Parte de [0021](./README.md) (versión 2, reordenado tras la [revisión adversarial](./revision-adversarial.md)). Nueve fases; cada una es entregable por sí sola y **deja la suite verde**. Los golden se regeneran con `GOLDEN_UPDATE=1` y **se revisan a mano** (el diff debe ser solo lo esperado de la fase). Cada fase termina con commits atómicos en inglés, el estado de esta tabla actualizado y la constante `CURRENT_PHASE` de F15 avanzada.

## Resumen

| Fase | Entrega | Rompe a los agentes | Depende de |
| :---: | :--- | :---: | :--- |
| 0 | Contrato, vocabulario, cobertura, sobre, errores base y pruebas de arquitectura escritas | no | — |
| 1 | Vista `list` completa sobre el sobre (con `--text`); `search` sigue vivo | no | 0 |
| 2 | Retirar `search` y cambiar la regla externa "Momento Cero" | **sí** (con pista de error) | 1 |
| 3 | `get`, `labels`, `projects`, `whoami` y demás lecturas en el sobre | no | 1 |
| 4 | Prerrequisitos de datos: defectos 0017, 0010 y 0022 | no | — (puede ir en paralelo a 1-3) |
| 5 | `report time` y `report flow` como vistas; `worklog check` en el modelo | **sí** (`report` pasa a grupo) | 3, 4 |
| 6 | Comando `sync` (`--history`) y retiro de flags de `list` | sí (con pista) | 1, 4 |
| 7 | Contrato de errores en todo el código | no | 0 |
| 8 | Sobre de resultado en las escrituras | no | 7 |

`report agenda` no aparece: la define el [RFC 0005](../0005-vista-personal-agenda-y-backlog/README.md) sobre este modelo y sus datos.

## Fase 0 · Contrato y vigilancia (sin cambio de comportamiento)

- **Entrega:** decisión estable del contrato en `docs/decisions/` (promueve [`contrato-json.md`](./contrato-json.md) para que F4 no dependa de un RFC cuyo estado cambia); `vocabulary.py` **completo** (derivado de los JSON reales de hoy: tickets, horas, flujo, comprobación, `get`, catálogos), `errors.py`, `coverage.py` con la regla de `complete`, `envelope.py` (con `validate` y degradación `internal`); mover `age_text` e `iso_utc` de `cache` a `timeutil`; `tests/test_architecture.py` con F1-F15 **escritas** (las de fases posteriores, saltadas bajo el trinquete F15).
- **Archivos:** capas 1 y 3 nuevas; `test_architecture.py`; enmienda de `ARCHITECTURE.md` y `__init__.py` **solo en lo que ya existe** (capa 1 con `vocabulary`/`errors`; la nueva nomenclatura se enmienda en la fase que la implementa).
- **Golden:** ninguno cambia.
- **Aceptación:** `test_docs`, `test_structure` y F1, F3 (sobre sintético), F4, F8, F13, F14, F15 verdes; vocabulario y contrato coinciden.
- **Riesgo:** diseñar el vocabulario sin usarlo. Mitigación: se valida contra los JSON reales de hoy (columna "Sustituye a").

## Fase 1 · `list` completa sobre el sobre (`search` sigue vivo)

- **Entrega:** `scope.py` (puro), `scope_flags.py`, `freshness.py` (`catalogs`, `ensure`), `store_issues.py`, `query_issues.py`, `render_issues.py`, `views.py` con la vista `list`; flags `--text`, `--limit`, `--offline`, `--verbose`; orden total con NULL al final. Los sincronizadores de `cache` devuelven `(estado, as_of)` y persisten `capped`/`stale` por proyecto. `list` sin ningún flag **deja de ir a la API**.
- **Golden:** `list_filters`, `read_list_search_labels_projects`, `help`, `errors_*`.
- **Aceptación:** F2, F3, F5 (caché envejecida), F6, F7 (dos zonas), F9, F12 activas y verdes para `list`; la ayuda global **medida** (≤ 280 tokens); el comportamiento de `search` cubierto por casos equivalentes de `list --text` (tokenización, respaldo LIKE, relevancia).
- **Riesgo:** churn de golden que oculta una regresión. Mitigación: revisar cada diff contra el vocabulario.

## Fase 2 · Retirar `search` y cambiar la regla externa

- **Entrega:** borrar `cmd_search`, `cached_issues`/`LIST_LIMIT` y el atajo numérico; reescribir `renamed.py`: añadir `EXAMPLES["report"]` (hoy `KeyError`), traducir flags en `RETIRED` (`search Q -p X --json` → `list --text Q -p X --json`), y reconciliar `SYNONYMS` (`sync` ya es sinónimo de `flush`); actualizar `SKILL.md` (la prueba `test_every_route_is_cited` exige citar toda ruta), `references/*` y `ARCHITECTURE.md`; **cambiar `rules/src/work.md` y regenerar con `make work`** ([`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md)).
- **Golden y pruebas:** `test_cli_tree` (TREE, LEAF_ARGS), `test_golden` (ROOT_COMMANDS), `test_offline_reads` (11 usos de `search`), `test_json_flag`, `test_outbox_flush`, `test_renamed`.
- **Aceptación:** el criterio `grep` **verificable** de [`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md); `plane-tracker search ...` termina con código 2 y la pista traducida; una sesión nueva de un agente ejecuta la regla nueva.
- **Riesgo:** agentes ya cargados con la regla vieja. Mitigación: la pista de `renamed.py`.

## Fase 3 · Lecturas restantes en el sobre

- **Entrega:** `get` (`coverage.source` = `api` o `snapshot`, sin `scope`), `labels`, `projects`, `whoami --json`, `attachment list` y `outbox list` con el sobre y los nombres del vocabulario.
- **Golden:** `get`, `read_*`, `whoami`, `outbox`, `attachment`.
- **Aceptación:** F3 y F5 extendidas a estas vistas; F6 cubre `attachment list`.

## Fase 4 · Prerrequisitos de datos (defectos)

- **Entrega:** corregir [0017](../../defects/0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md) (paginar y acotar la sincronización; quitar la lista fija de proyectos), [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) (**marca de sincronización por proyecto y periodo**, no global) y [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md) (procedencia: lo no medido no se presenta como medido).
- **Aceptación:** los criterios de cierre de cada defecto; con ellos, `coverage.complete` de `report time` puede ser `true`.
- **Riesgo:** sin esta fase, `report time` sería `null` para siempre y las horas por defecto parecerían medidas. Por eso la fase 5 **no puede empezar antes**.

## Fase 5 · `report` como grupo (`time`, `flow`) y `worklog check`

- **Entrega:** `store_worklogs`, `store_transitions`, `query_time`, `query_flow`, `render_time`, `render_flow`; `--from/--to/--week` comunes; `summary` en JSON (por día, proyecto y balde, con `undeclared`); cobertura de horas (`hours_local_only`, `hours_unsigned`, `hours_defaulted`, `pending_unpublished`); `--all-authors` retirado; `report flow` como `source: mixed` con `--offline`; `worklog check` adopta el alcance y el sobre; `report` sin vista → código 2 con pista (`renamed.py`: reescribir `_report` para traducir `--check`, `--flow`, `--sync`).
- **Golden:** `report*`, `report_flow`, `worklog_check`, `help`.
- **Aceptación:** F10, F11 activas; el filtro de proyecto es el mismo en las tres vistas; `flow` compara fechas en la zona declarada.

## Fase 6 · `sync` y retiro de flags de `list`

- **Entrega:** `cmd_sync` (`--history`, `--budget`, `-p`/`--all-projects`), definido en [`arbol-de-comandos.md`](./arbol-de-comandos.md); `list --refresh-history` y `--budget` se retiran con pista a `sync --history`. Se resuelve el nombre del módulo `sync.py` (worklogs) frente al comando.
- **Aceptación:** `sync` solo emite GET (F6); el historial sigue siendo reanudable y con presupuesto.

## Fase 7 · Contrato de errores en todo el código

- **Entrega:** `CliError` en las capas bajas (hoy 53 `sys.exit` en 16 archivos, incluidos `config`, `api`, `resolve`, `worklog`, `outbox`); `cli.main()` único captor; sobre de error en `--json`; registro completo de errores (incluidos los de escrituras); parser propio con `allow_abbrev=False` y error de uso en JSON. Se puede partir por familia de comandos.
- **Aceptación:** ningún `sys.exit(1)` fuera de `errors`/`cli`; F3 valida los sobres de error.

## Fase 8 · Sobre de resultado en las escrituras

- **Entrega:** `{status, action, ticket, uuid}` en `create`, `update`, `delete`, `link add`, `comment *`, `attachment *`; `status: queued` para comentarios encolados; el contrato se declara **estable** y la evolución pasa a ser aditiva.

## Seguimiento

| Fase | Estado | Commit o decisión |
| :---: | :--- | :--- |
| 0 | pendiente | |
| 1 | pendiente | |
| 2 | pendiente | |
| 3 | pendiente | |
| 4 | pendiente | |
| 5 | pendiente | |
| 6 | pendiente | |
| 7 | pendiente | |
| 8 | pendiente | |

Este RFC pasa a `implementado` solo cuando las nueve fases estén cerradas; hasta entonces ningún documento cita el modelo como existente.
