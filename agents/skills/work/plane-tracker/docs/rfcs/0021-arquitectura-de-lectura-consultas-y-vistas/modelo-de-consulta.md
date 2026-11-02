# Modelo de consulta

Parte de [0021](./README.md) (versión 2, tras la [revisión adversarial](./revision-adversarial.md)). Define las piezas, sus contratos, los invariantes y dónde viven en las capas de [`ARCHITECTURE.md`](../../../ARCHITECTURE.md).

## Flujo

```text
argv ─► cmd_* ─► freshness.catalogs(...)  ──► Catalogs (proyectos, estados, miembros, actor: lectura de SQLite; GET solo si vencieron)
            │                                       │
            │                                       ▼
            └─────────────────────────────► resolve_scope(args, Catalogs, View) ──► Scope   (puro: sin red, sin SQLite)
                                                    │
        freshness.ensure(view, Scope) ──► Coverage de adquisición   (única vía a la red de las vistas; solo GET)
                                                    │
        View.query(conn, Scope) ──► Result(rows, total, summary, coverage, extra_notes)     (solo lee SQLite)
                                                    │
        envelope.build(view, scope, result) ──► sobre (dict) ──┬─► --json: serializa
                                                              └─► texto: View.render(sobre)
```

Una consulta nunca imprime y un render nunca consulta: el texto sale **del mismo sobre** que el JSON, así que no pueden divergir.

## Contrato de adquisición

Toda la red de una lectura sale de `freshness` y es **solo GET**. Cada vista declara qué refresca y con qué política; el resto lo lee de SQLite.

| Vista | `freshness` refresca | Política | Red adicional | `coverage.source` |
| :--- | :--- | :--- | :--- | :--- |
| `list` | tickets de los proyectos del alcance; proyectos, estados, etiquetas y miembros si faltan | TTL de tickets 30 min, de catálogos 1 día; `--refresh` fuerza; `--offline` no refresca nada | ninguna | `cache` |
| `report time` | los worklogs del periodo y de los proyectos del alcance | marca de sincronización **por proyecto y periodo** (hoy es global: defectos 0010/0017) | ninguna | `local` (`cache` si sincronizó) |
| `report flow` | las transiciones de los tickets del alcance que falten o hayan cambiado | incremental por `plane_updated_at`; `--offline` usa solo lo almacenado | 1 GET de actividades por ticket pendiente | `mixed` |
| `report agenda` (la define [0005](../0005-vista-personal-agenda-y-backlog/README.md)) | tickets y worklogs (como `list` y `report time`) | las de ambos | ninguna | `mixed` |
| `worklog check` | **es una auditoría contra Plane**: compara filas locales con los comentarios | siempre red | 1 GET de comentarios por ticket | `api`; queda **fuera** de F5 (documentado) |
| `get` | el ticket y sus comentarios | API por diseño; instantánea local de respaldo | 1 a 2 GET | `api` o `snapshot` |

`--offline` (control de toda vista de caché) impide cualquier GET y devuelve lo local con su cobertura; sin él, un fallo de red degrada a lo local con `stale: true` en vez de fallar.

## Las piezas

### 1. Vocabulario (`vocabulary.py`, capa 1)
Fuente única y cerrada de: dimensiones y controles, relaciones de persona, nombres de campo por familia de resultado, códigos de nota y de error con severidad y remedio. Es datos puros: no importa nada del paquete. Especificación en [`contrato-json.md`](./contrato-json.md).

### 2. Alcance (`scope.py` puro; `scope_flags.py` para los flags)
```python
@dataclass(frozen=True)
class Scope:
    projects: tuple[ProjectRef, ...]      # (identificador, UUID), ya validados contra los catálogos
    ticket_person: PersonFilter | None    # relación con el ticket: assigned | created | involved
    hours_author: str | None              # UUID del autor de las horas (vistas de tiempo); None = sin filtro
    period: Period | None                 # desde/hasta inclusivos + zona horaria (IANA o desplazamiento) con que se interpretan
    state: str                            # "open" | "all"
    text: str | None
    order: str                            # orden total declarado, p. ej. "rank,-sequence" o "-updated,-sequence"
    limit: int | None                     # None en vistas de reporte
    offline: bool
    refresh: bool
```
- **Dimensiones** del alcance: `projects`, `person`, `period`, `state`, `text`. **Controles**: `limit`, `refresh`, `offline`, `verbose`. La matriz de [`arbol-de-comandos.md`](./arbol-de-comandos.md) usa estos dos grupos.
- `person` se reparte en `ticket_person` (qué tickets) y `hours_author` (de quién son las horas): `agenda` necesita ambos a la vez.
- `resolve_scope(args, catalogs, view)` es **puro**: valida contra `Catalogs` ya cargados y no toca red ni base. Proyecto desconocido → `unknown_project` con la lista de opciones; persona sin identidad → `actor_unknown`; periodo mal formado → `bad_period`. Ningún comando valida por su cuenta.
- `scope_flags.add_scope_args(parser, dims, controls)` declara **solo** los flags de lo que la vista acepta; lo no soportado no tiene flag y argparse lo rechaza (código 2). Hoy ya hay declaraciones de flags en librerías (`config.add_json_flag`, `list_filtered`, `attachments`); `scope_flags` las **centraliza** y se enmienda la regla de capas para permitir exactamente ese tipo de módulo.
- El parser raíz se crea con `allow_abbrev=False` (una abreviatura ambigua de un flag no puede cambiar de significado).
- **Periodo y zona:** el periodo se fija en el calendario local de quien lo pide y el sobre repite `period.tz`; las comparaciones con instantes UTC (`completed_at`) convierten primero. El orden es **total** (con desempate por `sequence_id` o `ticket`), nunca dependiente del orden de inserción.

### 3. Cobertura (`coverage.py`)
```python
@dataclass(frozen=True)
class Coverage:
    source: str                   # "cache" | "api" | "snapshot" | "local" | "mixed"; describe el ORIGEN de los datos, no la acción
    as_of: str | None             # ISO UTC del dato más antiguo usado
    age_s: int | None
    stale: bool                   # se sirvió vencido porque la red no respondió
    complete: bool | None         # True | False | None = NO VERIFICADO
    unavailable: tuple[str, ...]  # proyectos sin datos ni caché
    detail: dict                  # por vista: history {verified,total}, text_fields, hours_scope, capped, legacy...
```
**Regla de `complete`** (por vista; `None` nunca se renderiza como completo):

| Vista | `True` si... | `False` si... | `None` si... |
| :--- | :--- | :--- | :--- |
| `list` | todos los proyectos del alcance están dentro del TTL (o recién sincronizados), sin `legacy` ni `capped` | algún proyecto `unavailable` o `capped` | se sirvió vencido, o hay `legacy` (tickets sin datos de asignación) con filtro de persona |
| `report time` | la sincronización de horas está verificada para cada proyecto del alcance y todo el periodo | hay periodo o proyecto sin sincronizar | no se puede saber (marca global: hoy, siempre) |
| `report flow` | todos los tickets del alcance tienen transiciones al día (`plane_updated_at` igual) | faltan transiciones de algún ticket (`detail.history`) | — |
| `report agenda` (0005) | las dos fuentes son `True` | alguna es `False` | alguna es `None` |
| `get` | `source` = `api` | — | `source` = `snapshot` |

`Coverage.merge(*parts)`: `as_of` el más antiguo; `source` `mixed` si difieren; `complete` es `False` si alguna parte lo es, `None` si alguna es desconocida, `True` solo si todas lo son. Invariante **F14**: `complete: true` es **imposible** si hay una nota de severidad `warn`.

### 4. Notas derivadas
Las notas **no se escriben a mano**: `notes_from(coverage, scope, result)` las deriva (`cache_stale` de `stale`, `source_unavailable` de `unavailable`, `history_partial` de `detail.history`, `truncated` de `total > count`, ...). La consulta solo añade, vía `extra_notes`, las propias de su vista (p. ej. `hours_unsigned`, `hours_defaulted`), y cada una debe existir en el registro. Así hay **una sola fuente** por hecho.

### 5. Almacenes (`store_issues.py`, `store_worklogs.py`, `store_transitions.py`)
Repositorios **de solo lectura** sobre SQLite. Cada método devuelve filas ya en el vocabulario y su `Coverage`. Sin red ni `print`. Reemplazan los SQL sueltos de los `cmd_*`.

### 6. Frescura (`freshness.py`)
- `catalogs(conn, env, offline) -> Catalogs`: proyectos, estados, etiquetas, miembros y actor; lee SQLite y hace GET solo si vencieron (con degradación a lo almacenado).
- `ensure(conn, env, view, scope) -> Coverage`: aplica el contrato de adquisición de la vista. Cada proyecto se trata por separado: uno caído no aborta el resto; sin ninguno disponible, error `no_cache`.
- Los sincronizadores de `cache` y `sync` **devuelven estado** `(estado, as_of)` y persisten por proyecto si el resultado fue truncado (`capped`) o servido vencido, para que una lectura posterior pueda emitir la nota desde la caché.
- **Es la única vía a la red de las vistas** y solo emite GET (F6).

### 7. Consultas (`query_issues.py`, `query_time.py`, `query_flow.py`; `query_agenda.py` lo añade 0005)
Funciones `query(conn, scope) -> Result` que **solo leen SQLite** (a través de los almacenes). Reglas:
- Orden determinista, total y declarado en `scope.order`. Con texto: relevancia FTS y desempate `-sequence`. Sin texto: `plane_updated_at` descendente con **NULL al final** (cachés antiguas) y desempate por `sequence_id`; entre proyectos, el identificador del proyecto desempata antes que la secuencia.
- `total` es el recuento **antes** de `limit`; `count` es `len(results)`.
- El texto busca en **título y etiquetas**, no en la descripción; la cobertura lo declara (`detail.text_fields`).
- El atajo "el texto es un ID" **desaparece**: el ID va en `get`. Si el texto parece un ID (`PRJ-12`), la respuesta añade una nota con pista a `get`.

### 8. Vistas (`views.py`, `render_*.py`)
```python
@dataclass(frozen=True)
class View:
    name: str                       # "list", "report time", ...
    dims: frozenset[str]            # dimensiones que acepta
    controls: frozenset[str]        # controles que acepta
    defaults: dict                  # por vista: periodo, estado, límite
    acquisition: Acquisition        # qué refresca freshness (ver el contrato de adquisición)
    query: Callable[[Conn, Scope], Result]
    render: Callable[[dict], str]   # recibe el SOBRE, nunca la base de datos
```
El registro `VIEWS` las enumera; de él salen los flags de cada comando, la matriz del árbol y las pruebas de arquitectura. Sin clase base ni jerarquía: una vista es una tupla de metadatos y funciones.

### 9. Sobre (`envelope.py`)
`envelope.build(view, scope, result) -> dict` produce `plane-tracker/1`. **Valida en las pruebas** (F3) y, en producción, una deriva (campo fuera del vocabulario) **no tumba el comando**: se emite igual y se añade la nota `internal` con el detalle, para que un agente reciba datos y un humano vea el defecto. `envelope.dumps(doc)` serializa.

### 10. Errores (`errors.py`, capa 1)
`CliError(code, message, hint, exit_code)`; solo `cli.main()` lo captura. En `--json` imprime el objeto de error por stdout; en texto, mensaje y pista por stderr. Sustituye a los `sys.exit` repartidos (hoy 53 en 16 archivos, incluidos `config`, `api`, `resolve`, `worklog` y `outbox`), de modo que **las capas bajas lanzan `CliError`** en vez de terminar el programa. El registro de errores está en el contrato.

### 11. Política de stderr
En modo `--json`, lo que ya va en `notes`/`coverage` **no se repite por stderr** (un agente que mezcla ambos flujos pagaría el doble). En modo texto, los avisos siguen saliendo por stderr para humanos.

## Invariantes

| # | Invariante | Prueba |
| :--- | :--- | :--- |
| I1 | Una vista produce **un** sobre; el texto es `render(sobre)`. | F9 |
| I2 | Las vistas solo tocan la red vía `freshness`, y solo con GET. | F6 |
| I3 | No existe un `Result` sin `Coverage`. | F8 |
| I4 | Todo campo del sobre pertenece al vocabulario; todo código de nota y de error está registrado y documentado. | F3, F4 |
| I5 | El orden es total y declarado; mismo estado y reloj, mismos bytes, en cualquier zona horaria. | F7 |
| I6 | Una dimensión o control no soportado por una vista no tiene flag. | F2 |
| I7 | Toda lectura de la hora pasa por `clock`. | `test_structure` |
| I8 | Las vistas de caché funcionan sin conexión sobre una caché previa. | F5 |
| I9 | `complete: true` es incompatible con una nota `warn`. | F14 |
| I10 | Las notas se derivan de la cobertura; no hay dos fuentes del mismo hecho. | F13 |

## Dónde viven (capas)

Se enmienda `plane_cli/__init__.py`: la capa 1 pasa a incluir `vocabulary` y `errors` (datos y excepciones puros); la regla "capa 3 sin parsers" admite módulos de **declaración de flags compartidos** (`scope_flags`, y los ya existentes).

| Módulo | Capa | Puede importar | Notas |
| :--- | :---: | :--- | :--- |
| `vocabulary`, `errors` | 1 | nada del paquete | `config`, `api`, etc. pueden importar `errors` |
| `coverage` | 3 | `vocabulary` | |
| `scope` | 3 | `vocabulary`, `errors` | **puro**; no importa `resolve`, `db` ni `freshness` (corta el ciclo `scope`↔`freshness`) |
| `scope_flags` | 3 | `vocabulary`, `config` | solo declara flags |
| `timeutil` | 3 | `clock`, `vocabulary` | recibe `age_text` e `iso_utc` desde `cache` |
| `store_*` | 3 | `db`, `coverage`, `vocabulary` | solo lectura |
| `freshness` | 3 | `resolve`, `cache`, `sync`, `api`, `coverage` | única vía a la red |
| `query_*` | 3 | `store_*`, `scope`, `coverage`, `assignments`, `flow_metrics` | solo SQLite |
| `render_*` | 3 | `vocabulary`, `timeutil` | **prohibido** importar `sqlite3`, `os`, `clock`, `db`, `api`, `cache`, `resolve`, `store_*`, `freshness`, y recibir `conn` (F9) |
| `envelope` | 3 | `vocabulary`, `coverage`, `scope` | |
| `views` | 3 | `query_*`, `render_*`, `envelope`, `coverage` | el registro |
| `cmd_read`, `cmd_report`, `cmd_sync` | 4 | `views`, `scope`, `scope_flags`, `freshness`, `errors` | solo registran y llaman |

La tabla es **datos de la prueba F1**, no solo documentación. Absorbe: `list_filtered.py` (se reparte en `scope`, `store_issues`, `query_issues`, `render_issues`), la lógica de `cmd_search` y de `cmd_report`. `assignments.py` y `flow.py` se conservan como lógica de dominio. Todo archivo respeta 450 líneas y toda función 150.

## Lo que el modelo NO es

- No es un lenguaje de consultas ni un constructor de SQL genérico: cada tabla se consulta con su almacén.
- No fusiona `report time`, `flow`, `agenda` y `worklog check` en una sola consulta: tienen fuentes y costes distintos.
- Las escrituras solo comparten el contrato de errores y el sobre de resultado.
