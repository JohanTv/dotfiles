# Modelo de consulta

Parte de [0021](./README.md). Define las piezas, sus contratos, los invariantes y dónde viven en las capas de [`ARCHITECTURE.md`](../../../ARCHITECTURE.md).

## Flujo

```text
argv ──► cmd_* (registra flags desde View.dims) ──► resolve_scope() ──► Scope
                                                                         │
            freshness.ensure_fresh(Scope)  ◄── única vía a la red (GET de sincronización)
                          │  Coverage
                          ▼
   View.query(conn, Scope) ──► Result(rows, total, summary, coverage, notes)
                                        │
                          envelope.build(view, scope, result) ──► sobre (dict)
                                        │
                  ┌─────────────────────┴─────────────────────┐
             --json: serializa                         texto: View.render(sobre)
```

Una consulta nunca imprime y un render nunca consulta: el texto se produce **del mismo sobre** que el JSON, así que no pueden divergir.

## Las piezas

### 1. Vocabulario (`vocabulary.py`)
Fuente única y cerrada de: dimensiones (`projects`, `person`, `period`, `state`, `text`), relaciones de persona (`assigned`, `created`, `involved`, `author`), filtros de estado (`open`, `all`), nombres de campo de un ticket y de un registro de horas, códigos de nota y de error (con severidad y remedio). Ver [`contrato-json.md`](./contrato-json.md). Es datos puros: no importa nada del paquete.

### 2. Alcance (`scope.py`, `scope_flags.py`)
```python
@dataclass(frozen=True)
class Scope:
    projects: tuple[ProjectRef, ...]   # (identificador, UUID), ya validados contra Plane/caché
    person: PersonFilter | None        # relación + UUID del actor; el actor se exige al construirlo
    period: Period | None              # desde/hasta inclusivos, calendario local
    state: str                         # "open" | "all"
    text: str | None
    limit: int
    refresh: bool
```
- `resolve_scope(args, conn, dims)` valida **una vez**: proyecto desconocido → error `unknown_project` con la lista de opciones; persona sin identidad → `actor_unknown`; periodo mal formado → `bad_period`. Ningún comando valida por su cuenta.
- `scope_flags.add_scope_args(parser, dims)` declara **solo** los flags de las dimensiones que la vista acepta. Una dimensión no soportada no tiene flag: argparse la rechaza (código 2) en vez de ignorarla en silencio. Es el único módulo con argparse fuera de `config` (precedente: `config.add_json_flag`); se enmienda la regla de capas para decirlo.
- El alcance **se repite en la respuesta** (`scope` del sobre), de modo que cada salida es autodescriptiva y reproducible.

### 3. Cobertura (`coverage.py`)
```python
@dataclass(frozen=True)
class Coverage:
    source: str                   # "cache" | "api" | "snapshot" | "local" | "mixed"
    as_of: str | None             # ISO UTC del dato más antiguo usado
    age_s: int | None
    stale: bool                   # se sirvió vencido porque Plane no respondió
    complete: bool | None         # True | False | None = NO VERIFICADO
    detail: dict                  # por fuente: history {verified,total}, text_fields, hours_scope...
    unavailable: tuple[str, ...]  # proyectos sin datos ni caché
```
- **Tres valores de completitud**: `None` significa "no se midió" y **nunca se renderiza como completo** (P5).
- `Coverage.merge(*parts)` es conservador: el `as_of` más antiguo, `complete` es `False` si alguna parte lo es, `None` si alguna es desconocida, `True` solo si todas lo son.
- `Result` no se puede construir sin `Coverage` (el constructor lo exige).

### 4. Almacenes (`store_issues.py`, `store_worklogs.py`, ...)
Repositorios **de solo lectura** sobre SQLite (`issues_cache`, `issues_fts`, `assignment_events`, `worklogs`, `state_transitions`). Cada método devuelve filas ya en el vocabulario **y** su `Coverage`. Sin red, sin `print`. Reemplazan los SQL sueltos que hoy viven en cada `cmd_*`.

### 5. Frescura (`freshness.py`)
`ensure_fresh(conn, env, scope) -> Coverage`: decide por TTL o `--refresh` si sincronizar, llama a `resolve.sync_issues` por proyecto, y convierte `PlaneUnavailable` en cobertura `stale`/`unavailable` por proyecto (un proyecto caído no aborta el resto; sin ninguno disponible, error `no_cache`). **Es la única vía a la red de las vistas** y solo hace GET.

### 6. Consultas (`query_issues.py`, `query_time.py`, `query_flow.py`, `query_agenda.py`)
Funciones puras `query(conn, scope) -> Result`. Reglas:
- Orden **determinista y declarado**: con texto, relevancia (FTS) y desempate `sequence_id` descendente; sin texto, `plane_updated_at` descendente y desempate por `sequence_id`. El orden va en `scope.order`.
- `total` es el recuento **antes** de aplicar `limit`; `count` el de `results`. El truncado nunca es invisible (nota `truncated`).
- El texto busca en **título y etiquetas**; no indexa la descripción, y la cobertura lo declara (`detail.text_fields`).
- El atajo "el texto es un ID de ticket" **desaparece**: el ID va en `get`. Esto elimina el defecto del prefijo ignorado.

### 7. Vistas (`views.py`, `render_*.py`)
```python
@dataclass(frozen=True)
class View:
    name: str                       # "list", "report time", ...
    dims: frozenset[str]            # dimensiones del alcance que acepta
    defaults: dict                  # por vista: periodo, estado, límite
    query: Callable[[Conn, Scope], Result]
    render: Callable[[dict], str]   # recibe el SOBRE, nunca la base de datos
```
Un registro (`VIEWS`) las enumera. De él salen los flags de cada comando, la matriz de [`arbol-de-comandos.md`](./arbol-de-comandos.md) y las pruebas de arquitectura. **No hay clase base ni jerarquía**: una vista es una tupla de funciones y metadatos.

### 8. Sobre (`envelope.py`)
`envelope.build(view, scope, result) -> dict` produce el documento `plane-tracker/1` y **valida** sus claves contra el vocabulario antes de devolverlo (falla con un error de programación, no de usuario). `envelope.dumps(doc)` serializa. Ver [`contrato-json.md`](./contrato-json.md).

### 9. Errores (`errors.py`)
`CliError(code, message, hint, exit_code)`. `cli.main()` es el único sitio que lo captura: en modo `--json` imprime el objeto de error por stdout; en texto, el mensaje y la pista por stderr. Sustituye los `sys.stderr.write(...); sys.exit(1)` repartidos.

## Invariantes

| # | Invariante | Se verifica con |
| :--- | :--- | :--- |
| I1 | Una vista produce **un** sobre; el texto es `render(sobre)`. | F9 |
| I2 | Las vistas no tocan la red salvo vía `freshness`, y solo con GET. | F6 |
| I3 | No existe un `Result` sin `Coverage`. | F8 |
| I4 | Todo campo del sobre pertenece al vocabulario; todo código de nota y de error está registrado y documentado. | F3, F4 |
| I5 | El orden es determinista y está declarado; mismo estado, mismo sobre. | F7 |
| I6 | Una dimensión no soportada por una vista no tiene flag. | F2 |
| I7 | Toda lectura de la hora pasa por `clock` (regla vigente). | `test_structure` |
| I8 | Las lecturas funcionan sin conexión sobre una caché previa. | F5 |

## Dónde viven (capas)

Se mantiene el flujo de `plane_cli/__init__.py`. Todo el modelo es capa 3 (lógica reutilizable, sin `cmd_*`) salvo el registro de comandos.

| Módulo | Capa | Depende de | Notas |
| :--- | :---: | :--- | :--- |
| `vocabulary` | 1 | nada | datos puros |
| `errors` | 1 | `vocabulary` | |
| `coverage` | 3 | `vocabulary`, `clock` | |
| `scope`, `scope_flags` | 3 | `vocabulary`, `resolve`, `config`, `errors` | `scope_flags` es el único argparse nuevo |
| `store_*` | 3 | `db`, `coverage`, `vocabulary` | solo lectura |
| `freshness` | 3 | `resolve`, `cache`, `api`, `coverage` | única vía a la red |
| `query_*` | 3 | `store_*`, `scope`, `coverage` | puras |
| `render_*` | 3 | `vocabulary`, `timeutil` | **no** importan `db`, `api`, `cache`, `resolve` ni `store_*` (F9) |
| `envelope` | 3 | `vocabulary`, `coverage`, `scope` | valida |
| `views` | 3 | `query_*`, `render_*`, `envelope` | el registro |
| `cmd_read`, `cmd_report`, `cmd_sync` | 4 | `views`, `scope_flags`, `freshness`, `errors` | solo registran y llaman |

Absorbe: `list_filtered.py` (se reparte en `scope`, `store_issues`, `query_issues`, `render_issues`), la lógica de `cmd_search` y de `cmd_report`, y el cálculo por periodo duplicado. `assignments.py` y `flow.py` se conservan como lógica de dominio que los almacenes y consultas usan. Todo archivo respeta el tope de 450 líneas y toda función el de 150.

## Lo que el modelo NO es

- No es un lenguaje de consultas ni un constructor de SQL genérico: cada tabla se consulta con su almacén.
- No fusiona `report time`, `report flow`, `report agenda` y `worklog check` en una sola consulta: tienen fuentes y costes distintos (0 llamadas, N llamadas por ticket, caché). Comparten alcance, cobertura, sobre y errores.
- No toca las escrituras salvo el contrato de errores y el sobre de resultado (`status`, `action`, `ticket`).
