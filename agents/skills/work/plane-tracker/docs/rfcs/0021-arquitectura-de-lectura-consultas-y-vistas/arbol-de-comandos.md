# Árbol de comandos objetivo

Parte de [0021](./README.md) (versión 2). Se mantiene la regla de nomenclatura vigente (verbos del ticket planos en la raíz, `<sustantivo> <verbo>` para el resto) y se enmienda en lo que se indica.

## Árbol

La raíz conserva **18 entradas**: sale `search`, entra `sync`. El presupuesto de la ayuda global (280 tokens) hoy tiene **cero holgura** (1120 caracteres exactos); con las descripciones nuevas ("Reportes: time | flow", "Sincronizar con Plane: --history", `list` como "Listar y buscar tickets (caché local)") el cálculo del revisor da ~275 tokens. La fase que cambie la ayuda lo **mide** antes de fusionar; si no cabe, se acortan las descripciones, no se sube el tope.

| Entrada | Verbos | Notas |
| :--- | :--- | :--- |
| `get` | | un ticket con comentarios; sobre común (sin `scope`) |
| `list` | | **única** vista de tickets (absorbe `search`); caché con refresco por TTL |
| `create`, `update`, `delete` | | escrituras; sobre de resultado y errores comunes |
| `comment` | `add`, `edit`, `delete` | sin cambios de contrato salvo errores |
| `attachment` | `add`, `list`, `delete`, `replace` | `list` es una lectura de red (cae bajo F6) |
| `link` | `add` | |
| `outbox` | `list`, `flush`, `drop` | |
| `focus` | `set`, `clear`, `status` | |
| `worklog` | `propose`, `check` | `check` es auditoría contra Plane (N llamadas): se conserva aparte |
| `report` | `time`, `flow` | **grupo con vista obligatoria**; `time` es la vista que hoy es implícita |
| `sync` | | mantenimiento con coste en peticiones (definido abajo) |
| `handoff` | | |
| `labels`, `projects` | | catálogos |
| `whoami` | | gana `--json` |
| `health` | | |

`report agenda` **no es parte de este RFC**: la define el [RFC 0005](../0005-vista-personal-agenda-y-backlog/README.md) como una vista más del modelo (aquí solo se reserva su lugar: `Scope` ya distingue persona del ticket y autor de las horas).

## Qué comandos usan el sobre `plane-tracker/1`

| Comando | Sobre | Razón |
| :--- | :---: | :--- |
| `list`, `get`, `labels`, `projects`, `report time`, `report flow`, `worklog check` | lectura | son lecturas de datos |
| `create`, `update`, `delete`, `link add`, `comment add\|edit\|delete`, `attachment add\|delete\|replace`, `sync` | escritura | `status`, `action`, `ticket` |
| `attachment list`, `outbox list`, `whoami` | lectura | listas simples; `attachment list` además cae bajo F6 |
| `health`, `focus status`, `handoff`, `worklog propose` | **no** (mantienen su salida) | diagnóstico, estado de sesión y propuestas de medición: no son lecturas de tickets ni de horas; **sí** adoptan el contrato de errores |

## Matriz de dimensiones y controles por vista

Las **dimensiones** (`projects`, `person`, `period`, `state`, `text`) acotan el contenido; los **controles** (`limit`, `refresh`, `offline`, `verbose`) no. `●` acepta, `○` fijada por la vista, `—` sin flag (argparse la rechaza).

| Vista | projects | person | period | state | text | limit | refresh | offline |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `list` | ● | ● ticket: `--mine`, `--created`, `--involved` | — | ● `--open` | ● `--text` | ● | ● | ● |
| `report time` | ● | ○ autor = yo | ● | — | — | — (sin límite) | ● | ● |
| `report flow` | ● | — | ● | ○ cerrados en el periodo | — | — (sin límite) | ● | ● |
| `worklog check` | ● | — | ● | — | — | — | — (siempre red) | — |

- `-p` y `--all-projects` en **todas** las vistas que aceptan proyectos; el periodo es `--from/--to/--week` en todas las que lo aceptan. Los valores por defecto son por vista (`View.defaults`).
- Se **retira `--all-authors`** (propuesta): el sync solo ingiere las horas propias, así que no hay datos de otros, y mostrarlos invertiría P2/P3. Las horas con autor nulo se **excluyen** de "mías" y se cuentan en la nota `hours_unsigned`.
- Se retiran `--today` y `--date` (una sola forma de declarar el periodo) y, de `list`, `--refresh-history` y `--budget`. Los flags actuales `--track` y `--worker-type` de `report` se **conservan** como filtros de `report time` (la matriz los lista como dimensión `track` del registro de horas, no se pierden en silencio).
- La validación de proyecto usa los catálogos cargados: no añade red a los reportes locales.

## `list`: texto, orden y estado

- `list --text "<texto>"` busca en título y etiquetas (FTS con la tokenización y palabras vacías actuales) y ordena por relevancia; sin texto, por recencia. Se combina con cualquier otro flag.
- **Estado por defecto `all`** en todos los modos (la búsqueda anti-duplicados debe ver cerrados y cancelados); `--open` es explícito.
- **Orden total**: con texto, relevancia y desempate `-sequence`; sin texto, `plane_updated_at` descendente con NULL al final, desempate por proyecto y secuencia. Este RFC **sustituye** lo dicho en la decisión [0019](../../decisions/0019-filtros-de-persona-y-historial-de-asignacion.md) sobre dónde viven los filtros y el orden por `sequence_id`, y fusiona `search` en `list`; el resto de 0019 (definiciones de "involucrado", cobertura de historial, autoría) se mantiene.
- Sin consejo de rama ni prosa imperativa: con `total: 0` el agente decide. La política vive en `SKILL.md` y en la regla externa.
- `list "texto"` posicional no existe: error de uso con pista a `--text`.

## `sync`

`plane-tracker sync [--history] [--budget N] [-p P | --all-projects]`: **mantenimiento con coste en peticiones**, nunca implícito en una lectura.
- Sin `--history`: sincroniza tickets y los worklogs de los comentarios de los proyectos del alcance (lo que hoy hace `report --refresh` y `sync.py`), con la marca por proyecto y periodo de [`modelo-de-consulta.md`](./modelo-de-consulta.md).
- Con `--history`: trae el historial de asignación y las transiciones pendientes, con presupuesto, parada ante 429 o circuito abierto y reanudación.
- Es una escritura **local** y GET remotos; no toca Plane (cae bajo F6).

## Nomenclatura: qué se enmienda

| Regla vigente | Enmienda |
| :--- | :--- |
| 1. La raíz solo tiene los verbos del ticket (`search`, `get`, `list`, ...) | Sin `search`. Se añade `sync`. |
| 3. Un flag nunca elige la operación; la operación es el verbo o la vista posicional `report flow` | Las vistas de `report` son sustantivos y **obligatorias** (`report time`, no `report` a secas). |
| 5. Nombres retirados terminan con código 2 y pista | `search` → `list --text` (con traducción de `-p`, `--refresh`, `--json`); `report` sin vista → `report time`; `list --refresh-history` → `sync --history`. Requiere reescribir `renamed.py` (ver el plan). |
| 7. Se mantienen los flags que no eligen operación y las claves JSON | Las claves JSON **cambian una vez**, al declarar `plane-tracker/1`; después rige la evolución aditiva. |

## Qué desaparece del código

`cmd_search` y su atajo numérico, el camino API de `list` (`?limit=50`, imprime 15), `cached_issues()` y `LIST_LIMIT`, `list_filtered.py` (repartido en el modelo), el consejo de rama de la búsqueda, `add_period_args` en `cmd_report` (sube a `scope_flags`), las dos implementaciones del filtro `-p` de los reportes y `--all-authors`.
