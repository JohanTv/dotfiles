# Árbol de comandos objetivo

Parte de [0021](./README.md). Se mantiene la regla de nomenclatura vigente (verbos del ticket planos en la raíz, `<sustantivo> <verbo>` para el resto) y se enmienda en lo que se indica.

## Árbol

La raíz conserva **18 entradas**: sale `search`, entra `sync`. El presupuesto de la ayuda global (280 tokens) no se toca; una prueba lo comprueba en cada fase.

| Entrada | Verbos | Notas |
| :--- | :--- | :--- |
| `get` | | un ticket con comentarios; sobre común con `coverage.source` |
| `list` | | **única** vista de tickets (absorbe `search`); solo caché |
| `create`, `update`, `delete` | | escrituras; adoptan el sobre de resultado y errores |
| `comment` | `add`, `edit`, `delete` | sin cambios |
| `attachment` | `add`, `list`, `delete`, `replace` | sin cambios |
| `link` | `add` | sin cambios |
| `outbox` | `list`, `flush`, `drop` | sin cambios |
| `focus` | `set`, `clear`, `status` | sin cambios |
| `worklog` | `propose`, `check` | `check` es auditoría contra Plane (N llamadas): se conserva aparte |
| `report` | `time`, `flow`, `agenda` | **grupo con vista obligatoria**; `time` es la vista que hoy es implícita |
| `sync` | | mantenimiento con coste en peticiones (`--history [--budget N]`); sale de `list` |
| `handoff` | | sin cambios |
| `labels`, `projects` | | catálogos; adoptan el sobre |
| `whoami` | | gana `--json` |
| `health` | | sin cambios de contrato |

## Matriz de dimensiones por vista

`●` acepta, `○` fija por la vista, `—` no existe como flag (argparse la rechaza).

| Vista | proyectos | persona | periodo | estado | texto | límite | refresh |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `list` | `-p`, `--all-projects` | `--mine`, `--created`, `--involved` | — | `--open` | `--text` | `--limit` | `--refresh` |
| `report time` | `-p`, `--all-projects` | ○ autor = yo; `--all-authors` | `--from`, `--to`, `--week` | — | — | — | `--refresh` |
| `report flow` | `-p`, `--all-projects` | — | `--from`, `--to`, `--week` | ○ cerrados en el periodo | — | — | `--refresh` |
| `report agenda` | `-p`, `--all-projects` | ○ asignado a mí | `--week` | ○ abiertos | — | `--limit` | `--refresh` |
| `worklog check` | `-p`, `--all-projects` | — | `--from`, `--to`, `--week` | — | — | — | — |

- **Un solo vocabulario de flags**: `-p`/`--all-projects`, `--from`/`--to`/`--week`, `--limit`, `--refresh`, `--json` significan lo mismo en todas las vistas que los aceptan. Los periodos por defecto son por vista y se declaran en `View.defaults` (`report time`: hoy).
- **Se retiran** `--today` y `--date` (una sola forma de declarar el periodo) y, de `list`, `--refresh-history` y `--budget` (pasan a `sync --history`).
- **Validación de proyecto en todas las vistas** con la misma pista (`Opciones: ...`); hoy `report*` no valida.

## `list`: texto y orden

- `list --text "<texto>"` busca en título y etiquetas (FTS con tokenización y palabras vacías actuales) y ordena por relevancia; sin `--text` ordena por recencia. Se combina con cualquier otro flag: `list --text sms --mine --open`.
- El **estado por defecto es `all`** en todos los modos (la búsqueda anti-duplicados debe ver cerrados y cancelados); `--open` es explícito. Para "¿ya existe esto?" en toda la organización: `list --text "<intención>" --all-projects`.
- Sin consejo de rama ni prosa imperativa en la salida. Con `total: 0` el agente decide si propone un ticket nuevo (la política vive en `SKILL.md` y en la regla externa, no en los datos).
- `list "texto"` posicional **no existe**: un argumento sin flag es un error de uso con pista a `--text`.

## Nomenclatura: qué se enmienda

| Regla vigente | Enmienda |
| :--- | :--- |
| 1. La raíz solo tiene los verbos del ticket (`search`, `get`, `list`, ...) | Sin `search`. Se añade `sync`. |
| 3. Un flag nunca elige la operación; la operación es el verbo o la vista posicional `report flow` | Las vistas de `report` son sustantivos y **obligatorias** (`report time`, no `report` a secas). |
| 5. Nombres retirados terminan con código 2 y pista | `search` → pista a `list --text`; `report` sin vista → pista a `report time`; `list --refresh-history` → pista a `sync --history`. |
| 7. Se mantienen los flags que no eligen operación y las claves JSON | Las claves JSON **sí cambian** una vez, al declarar `plane-tracker/1` (ver el contrato); a partir de ahí rige la evolución aditiva. |

## Qué desaparece del código

`cmd_search` y su atajo numérico, el camino API de `list` (`?limit=50`, imprime 15), `cached_issues()` y `LIST_LIMIT`, `list_filtered.py` (repartido en el modelo), el consejo de rama en la salida de búsqueda, `add_period_args` en `cmd_report` (sube a `scope_flags`), y las dos implementaciones del filtro `-p` de los reportes.
