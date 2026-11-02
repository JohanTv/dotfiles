# Arquitectura del CLI `plane-tracker`

Documento para quien modifica el código. El uso del CLI (comandos, flags, protocolo de bitácoras) está en `SKILL.md`.

El CLI es de solo biblioteca estándar de Python (3.10+). `scripts/plane.py` es el punto de entrada: inserta su propio
directorio real en `sys.path`, importa `plane_cli.cli.main` y lo ejecuta. El código vive en el paquete plano
`scripts/plane_cli/`; `session_clock.py` y `flow_metrics.py` son módulos independientes de `scripts/` (lectura de
transcripts de agentes y cálculo de flujo) que el paquete importa como módulos de primer nivel.

## Mapa de módulos

El tope duro por archivo es de 450 líneas y lo verifica `tests/test_structure.py`.

| Módulo | Responsabilidad |
|---|---|
| `plane.py` | Punto de entrada: ajusta `sys.path` y llama a `cli.main()`. |
| `plane_cli/__init__.py` | Docstring con el mapa de capas y módulos. |
| `plane_cli/config.py` | `CACHE_DIR`, rutas derivadas (`db_file()`, `request_log()`, `proposal_file()`), `local_midnight_utc()`, `positive_int()`, `add_json_flag()`, carga de `~/.zshrc.local` y `get_env_or_fail()`. |
| `plane_cli/clock.py` | Reloj central, única fuente de la hora real: `timestamp()` (la primitiva) y, derivadas de ella, `now()` (UTC con zona), `local_now()` (local sin zona) y `local_today()`. |
| `plane_cli/vocabulary.py` | Contrato `plane-tracker/1` como datos puros ([decisión 0025](docs/decisions/0025-contrato-json-de-lectura.md)): familias de campos, resúmenes, registro de notas, errores y códigos de comprobación; `field_spec()`. |
| `plane_cli/errors.py` | `CliError(code, message, hint, exit_code, detail)`: error de comando con código registrado (`to_dict()`, `render()`); todavía no sustituye a los `sys.exit`. |
| `plane_cli/db.py` | Conexión SQLite (WAL, directorio de caché 0700 y base 0600), `ensure_columns()`, esquema por partes (`init_core_tables()`, `init_catalog_tables()`, `init_issue_tables()`, `init_search_index()`, `init_outbox_tables()`...) y `init_db()` que las orquesta. |
| `plane_cli/circuit.py` | Circuito de fallo rápido entre procesos (`circuit.json` con flock), excepción `PlaneUnavailable` y su mensaje (`format_unavailable()`). |
| `plane_cli/api.py` | `api_request()`: clasificación de fallos, reintentos acotados, circuito, `PLANE_OFFLINE`, sondeo (`probe_plane()`), `log_request()` (JSONL de latencias) y `rate_limit()` (cabeceras `X-RateLimit-*` de la última respuesta, solo observadas). |
| `plane_cli/mdhtml.py` | `markdown_to_html()`: subconjunto de Markdown que renderiza Plane CE. |
| `plane_cli/cache.py` | Lecturas desde la caché local cuando Plane no responde: aviso de antigüedad, sincronización de tickets, snapshots de `get` y `issue_stub()`. |
| `plane_cli/resolve.py` | Proyectos, tickets, estados, etiquetas y usuario activo contra Plane, con caché SQLite; `detect_ticket_from_git()` y `local_ticket_label()`. |
| `plane_cli/timeutil.py` | Aritmética de horarios, unión de intervalos (medida de Klee), fusión diaria de worklogs, `render_day_block()`, `age_text()` e `iso_utc()`. |
| `plane_cli/coverage.py` | `Coverage`, `Result` (no existe sin cobertura), regla de `complete` por vista (`complete_list()`...) y notas derivadas (`notes_from()`, `build_notes()`); aún sin consumidores. |
| `plane_cli/envelope.py` | Sobre `plane-tracker/1`: `build()`, `validate()`, `validate_error()` y `dumps()`; en producción una deriva degrada con la nota `internal`; aún sin consumidores. |
| `plane_cli/worklog.py` | Bloque oculto `PLANE_WORKLOG_METADATA`, `upsert_worklog()`, `check_worklogs()`, `reject_placeholders()` y `PLACEHOLDER`. |
| `plane_cli/outbox.py` | Cola de salida de `comment add`: `publish_comment()` (guardado previo), reclamo atómico, entrega idempotente (`deliver()`), `list_items()`, `drop_item()` y conteos. |
| `plane_cli/outbox_flush.py` | `flush_items()`: orden, límites, resolución memoizada del ticket y reglas de parada. |
| `plane_cli/create_guard.py` | Guarda de `create` contra tickets duplicados: compara el título con la caché local y marca los envíos sin confirmar. |
| `plane_cli/sync.py` | `sync_remote_worklogs()`: comentarios de Plane a SQLite sin pisar registros en cola. |
| `plane_cli/proposal_store.py` | `last_proposal.json`: guardar, leer, consumir y bloquear entre procesos. |
| `plane_cli/proposals.py` | Medición de la sesión del agente, ventanas, `build_proposal()`, `build_split()` y su impresión. |
| `plane_cli/flow.py` | Lead/cycle time y esfuerzo por ticket, y la vista `report flow`. |
| `plane_cli/renamed.py` | `suggestion(argv, tree)`: pista de error para nombres retirados, verbos ausentes o mal escritos. |
| `plane_cli/attachments.py` | Subida firmada, borrado y listado de adjuntos; grupo `attachment` (`add`, `list`, `delete`, `replace`). |
| `plane_cli/cmd_comment.py` | Comando `comment add`. |
| `plane_cli/cmd_comment_ops.py` | Comandos `comment edit`, `comment delete` y `worklog propose`. |
| `plane_cli/cmd_tickets_write.py` | Comandos `create`, `update` y `link add`. |
| `plane_cli/cmd_delete.py` | Comando `delete`: decide con los comentarios del ticket (paginados) unidos a lo local, falla cerrado y limpia lo local; sin `--yes` solo informa. |
| `plane_cli/cmd_read.py` | Comandos `get`, `list` (orquesta catálogos, alcance, frescura, consulta y sobre; absorbe al retirado `search`), `labels`, `projects` y `whoami`. |
| `plane_cli/scope.py` | `Scope`, `ProjectRef` y `resolve_scope()`: alcance validado, **puro** (sin red ni SQLite), contra catálogos ya cargados; lanza `CliError` (`unknown_project`, `actor_unknown`) con pista. |
| `plane_cli/scope_flags.py` | `add_scope_args()` y `flags_for()`: cada vista solo declara los flags de sus dimensiones y controles. |
| `plane_cli/freshness.py` | `Env`, `catalogs()` y `ensure()`: única vía a la red de las vistas, solo GET; cada proyecto por separado (403 y caídos pasan a la cobertura). |
| `plane_cli/store_issues.py` | Lecturas de solo lectura de `issues_cache` (con FTS), `issue_sync` y datos de personas. |
| `plane_cli/query_issues.py` | Consulta de `list`: selección por persona y estado, orden total, filas del vocabulario `ticket` y `Result` con cobertura y `complete`. |
| `plane_cli/render_issues.py` | Texto de `list` a partir del sobre (nunca de la base de datos). |
| `plane_cli/views.py` | `View` y `VIEWS`: registro de vistas de lectura (hoy solo `list`). |
| `plane_cli/history_sweep.py` | Barrido de `list --refresh-history` (se retira en la fase 6). |
| `plane_cli/assignments.py` | Historial de asignación medido (`assignment_events`), su cobertura y el barrido con presupuesto (`--refresh-history`). |
| `plane_cli/cmd_report.py` | Comandos `report` (actividad; `report flow` delega en `flow`) y `worklog check`. |
| `plane_cli/cmd_outbox.py` | Comandos `outbox list`, `outbox flush` y `outbox drop`. |
| `plane_cli/cmd_ops.py` | Comandos `health`, `focus set\|clear\|status` y `handoff`, con sus ayudantes de git. |
| `plane_cli/cli.py` | Parser raíz, `COMMANDS` (árbol ordenado), `add_group()`, `command_tree()`, aviso de pendientes y `main()`. |

## Capas y regla de dependencias

1. `config`, `clock`, `vocabulary`, `errors`: la capa 1 solo importa de la capa 1 (`vocabulary` no importa nada; `errors` solo `vocabulary`).
2. `db`, `circuit`, `api`: dependen de `config` (`api` también de `circuit`).
3. Lógica reutilizable (`mdhtml`, `cache`, `resolve`, `timeutil`, `coverage`, `envelope`, `worklog`, `outbox`, `outbox_flush`, `create_guard`, `sync`,
   `proposal_store`, `proposals`, `flow`, `attachments`, `renamed`): importan de capas 1 y 2 y entre sí en una sola dirección. Salvo `attachments` (grupo
   `attachment`) y `flow` (`report flow`), que además contienen el comando que los usa, no definen parsers.
4. `cmd_*`: importan de las capas 1 a 3; **nunca** se importan entre sí ni importan `cli`.
5. `cli`: importa los `cmd_*`, `attachments`, `renamed` y `outbox` para registrar el árbol de comandos, consultar las pistas y avisar de los registros sin publicar.

Ninguna biblioteca importa un `cmd_*`. No hay ciclos de import. `tests/test_structure.py` lo verifica con un análisis del
AST, además de los nombres globales no definidos, el tamaño de archivos (450 líneas) y de funciones (150 líneas) y que
ningún módulo se llame como uno de la biblioteca estándar (el directorio de scripts va primero en `sys.path`, así que
un `http.py` o `types.py` sombrearía el módulo estándar).

Los módulos se importan siempre por nombre explícito (`from plane_cli.resolve import resolve_issue`), nunca con `*`.

## Convenciones

- **Rutas solo por `config`, hora solo por `clock`.** El código lee `config.CACHE_DIR` / `db_file()` / `request_log()` /
  `proposal_file()` y `clock.timestamp()` / `now()` / `local_now()` / `local_today()` por atributo del módulo en cada
  llamada; nunca `from plane_cli.clock import now`. Así un test sustituye `config.CACHE_DIR` o `clock.timestamp` y el
  cambio llega a todos los módulos. **Ningún otro archivo lee la hora real** (`datetime.now`, `time.time`...): lo
  verifica `tests/test_structure.py` con un presupuesto de 0. `time.monotonic` (tiempo transcurrido) y `time.sleep` no son
  "la hora" y no pasan por `clock`. No hay variable de entorno ni modo de pruebas que fije la hora: permitiría falsificar
  las marcas del worklog.
- **Idioma:** mensajes de usuario, comentarios y documentación en español; flags e identificadores internos en inglés.
- **Comentarios:** concisos y agnósticos; explican el porqué de una restricción vigente, no la historia del cambio.
- **Docstring de cabecera** en cada módulo: responsabilidad, qué expone y qué no hace.
- **Firma de los comandos:** `cmd_x(args, conn, base_url, api_key, workspace, default_project_id)`, aunque el comando
  no use todos los parámetros. `cli.main()` los llama como `args.handler(...)`.
- **Registro de subcomandos:** cada comando o verbo tiene `register_<comando>[_<verbo>](sub)` que define su parser y hace
  `set_defaults(handler=...)`; el handler es `cmd_<comando>[_<verbo>]`. Ningún handler lee `args.command` ni `args.verb`.

## Nomenclatura de comandos

El árbol se declara en `COMMANDS` (`cli.py`); su orden es el de `--help`. Cada entrada es un registrador (comando de la
raíz) o una tupla `(nombre, ayuda, registradores)` que `add_group()` convierte en un grupo `<sustantivo> <verbo>`: el
verbo es obligatorio (`dest="verb"`, `required=True`) y el usage lista los verbos (`{add,edit,delete}`).

Reglas:

1. La raíz solo tiene los verbos del ticket (`get`, `list`, `create`, `update`), `handoff`, los catálogos en
   plural (`labels`, `projects`), los diagnósticos (`whoami`, `health`) y `report`.
2. Toda otra familia es un grupo `<sustantivo singular> <verbo>`, aunque tenga un solo verbo (`link add`).
3. Un flag nunca elige la operación: la operación es el verbo (o la vista posicional `report flow`).
4. Verbos: `add`, `list`, `edit`, `delete`, `replace`, `flush`; marcas: `set`, `clear`, `status`; derivados: `propose`, `check`.
5. Los sinónimos de verbo y los nombres retirados no son alias: terminan con código 2 y una pista (`renamed.py`).
6. El ID requerido de un hijo es posicional (`attachment delete ISSUE ID`); si es opcional (por defecto, el último
   propio) es un flag (`--comment-id`).
7. Se mantienen los flags que no eligen operación y las claves JSON.

`--json` es global: `add_json_flag()` lo declara con `default=argparse.SUPPRESS` en la raíz, oculto en cada grupo y en
cada hoja que produce JSON. Sin valor por defecto, el último nivel que lo vea no pisa a los anteriores, y
`--json comment add`, `comment --json add` y `comment add --json` valen igual. Los handlers lo leen con
`getattr(args, "json", False)`; una hoja sin `--json` propio acepta el de la raíz y lo ignora.

`main()` llama primero a `renamed.suggestion(argv, command_tree(parser))`: `command_tree()` deriva `{comando: (verbos)}`
del propio parser, así que `renamed.py` no duplica el árbol ni importa `cli`. Si devuelve texto, se imprime como
`plane-tracker: error: <texto>` con código 2, antes de validar el entorno.

## Modo sin conexión

**Transporte (`api`, `circuit`).** Todo acceso a Plane pasa por `api_request()`. Un fallo transitorio (502/503/504,
timeouts, conexión rechazada o cortada, DNS, fallo de handshake TLS, respuesta ilegible) lanza `PlaneUnavailable`, que
lleva `kind`, `delivered` (`"no"`: la petición no llegó a enviarse; `"unknown"`: pudo procesarse) y el `method` de la
petición. Los errores definitivos (4xx, 500, certificado TLS no verificable) imprimen el error y terminan con código 1 sin
contar para el circuito. Solo los GET se reintentan (una vez, nunca tras un timeout); el 429 se reintenta con cualquier
método porque la petición no se procesó. `PLANE_OFFLINE=1` impide cualquier acceso a la red.
El circuito (`<CACHE_DIR>/circuit.json`, compartido entre procesos con flock) se abre tras 2 fallos consecutivos dentro de
120 s; abierto, las llamadas fallan sin tocar la red hasta que vence el enfriamiento (30, 60, 120 y 300 s según las sondas
fallidas), cuando un solo proceso sondea `GET /users/me/`. `outbox flush` sondea siempre (`probe_plane(force=True)`).

**Lecturas (`cache`).** Con red, los TTL siguen mandando. Ante `PlaneUnavailable`, `list`, `get`, `labels` y
`projects` responden con lo local aunque haya vencido, con el aviso de antigüedad en stderr; sin nada local terminan con
código 3.

**Guarda de duplicados en `create`.** Antes de enviar, `create` compara el título (sin distinguir mayúsculas ni espacios repetidos) con los tickets del proyecto creados en las últimas 24 h, usando solo la caché local. El envío deja una marca en `sync_metadata` que se borra al confirmarse el resultado (éxito, error definitivo o petición que no salió); si el POST queda sin confirmar, la marca sobrevive y el siguiente `create` del mismo título refresca la caché antes de comparar: si el ticket existe lo rechaza, y si no existe borra la marca y permite el reintento. `--allow-duplicate` omite la comparación.

**Cola de salida (`outbox`, `outbox_flush`).** Solo `comment add` se encola; `update`, `create`, `link add`,
`comment edit|delete` y `attachment *` fallan con código 3. La cola vive en la tabla SQLite `outbox` (texto de
comentarios: por eso el directorio de caché es 0700 y la base 0600; el payload nunca incluye la API key).

- *Guardado previo.* `outbox.publish_comment()` inserta el item `pending` y la fila provisional de `worklogs` (sin
  `plane_comment_id`, misma clave que `wl_*` del item) en una sola transacción **antes** del POST. Así lo encolado sigue
  contando como registrado (`session_coverage`, `report`) y no hay ventana en la que Plane tenga el comentario y la base
  local no. Límites: 64 KB por comentario y 200 items abiertos; una clave de worklog (ticket, track, fecha, inicio) solo
  admite un item abierto (índice único parcial).
- *Idempotencia.* Cada comentario lleva un `client_id` determinista (`pt-` + 20 hex del hash de ticket, track, fecha,
  inicio y texto visible) dentro de su bloque oculto y como `external_id` del POST (`external_source="plane-tracker"`).
  Un 409 con el `id` del comentario existente cuenta como enviado.
- *Entrega ambigua.* Un item con `maybe_delivered=1` (el POST pudo llegar) o en `sending` con el lease vencido (180 s) no
  se reenvía sin antes buscar su `client_id` en los comentarios del ticket (GET paginado, hasta 10 páginas, en el HTML o
  en `external_id`). La ambigüedad solo se limpia al enviarse o descartarse. Un comentario borrado a mano en Plane mientras
  seguía en la cola con `maybe_delivered=1` puede recrearse una vez.
- *Reclamo atómico.* `claim()` (`BEGIN IMMEDIATE` + `UPDATE` a `sending` con lease) deja pasar a un solo proceso por item.
- *Flush.* Orden por `id`, 25 por ejecución, 1 s entre items; omite los de más de 7 días (salvo `--include-old`) y poda los
  `sent`/`dropped` de más de 30 días. Un fallo transitorio detiene el flush (código 3); un error definitivo (400, 403,
  404, 422, 500) deja el item en `failed` con su `last_error` y sigue (código 1); un 401 lo detiene todo (código 1).
- *Sync.* `sync_remote_worklogs()` vincula y marca `sent` un comentario remoto con el `client_id` del item abierto de su
  clave, y omite (con aviso) el que coincide con la clave pero es de otro. `worklog check` marca esas filas como `pending`
  (aviso, no inconsistencia) y `report` avisa de los registros del periodo sin publicar.
- *Avisos.* `cli.main()` imprime por stderr, una vez y salvo en `outbox *`, cuántos registros siguen sin publicar. No hay
  envío automático: la cola solo se vacía con `outbox flush`.

**Códigos de salida.** 0 éxito (también un comentario encolado); 1 error definitivo, de validación, registros `failed` o
inconsistencias de `worklog check`; 2 uso; 3 Plane no disponible.

**Variables.** `PLANE_OFFLINE=1`: ninguna petición sale (todo lo que necesita Plane termina con código 3 y `comment add`
encola). `PLANE_NO_QUEUE=1`: `comment add` falla con código 3 en lugar de encolar, sin dejar item ni fila provisional.

## Agregar un comando

1. Decidir su lugar según las reglas de nomenclatura: comando de la raíz o verbo de un grupo (nuevo o existente).
2. Crear (o ampliar) un `plane_cli/cmd_x.py` con `cmd_nombre(args, conn, base_url, api_key, workspace, default_project_id)`
   y `register_nombre(sub)`, que añade el parser (con `help` de una línea de hasta 60 caracteres sin punto final; el
   texto largo va en `description=`), declara `--json` con `add_json_flag()` si produce JSON y termina en
   `set_defaults(handler=cmd_nombre)`. Si el archivo supera las 450 líneas, o la lógica es reutilizable por otros
   comandos, esa lógica va a un módulo de la capa 3.
3. Añadir el registrador a `COMMANDS` en `cli.py`, en la posición en que debe aparecer en `--help`: suelto si es un
   comando de la raíz, dentro de la tupla de su grupo si es un verbo (un grupo nuevo añade `(nombre, ayuda, (...))`).
4. Actualizar `TREE` en `tests/test_cli_tree.py` y, en `tests/test_golden.py`, `ROOT_COMMANDS` o `GROUPS` (alimentan el
   `--help` de cada ruta) y un escenario con su salida, peticiones al servidor falso y filas locales. Generarlo con
   `GOLDEN_UPDATE=1` y revisar el diff a mano.
5. Documentar el comando en `SKILL.md` (sección de comandos disponibles).

## Tests

Desde el directorio del skill:

```bash
python3 -m unittest discover -s tests   # secuencial: la referencia y el único modo para GOLDEN_UPDATE=1
python3 tests/run_parallel.py           # en paralelo, cada trabajo con su HOME temporal
```

- **`tests/run_parallel.py`** (solo biblioteca estándar): un proceso por trabajo (los módulos pesados, por método), sin
  variables `PLANE_*` y con prioridad baja (`--nice`). `-j N` limita los procesos, un texto filtra módulos y
  `--freeze <ISO con zona>` congela la hora real del propio proceso de pruebas: toda la suite debe pasar con cualquier
  instante. Sale con 1 si algún trabajo falla.
- **Golden (`test_golden.py`).** Ejecuta el CLI por subproceso contra un servidor Plane falso (`http.server` en
  127.0.0.1) con `HOME` temporal, `TZ=UTC` y credenciales ficticias, y compara salida, código de salida, peticiones
  enviadas y filas locales con `tests/golden/*.txt`. Solo se normaliza lo no determinista por naturaleza (puertos, rutas
  temporales, SHA, ids al azar y latencias; `tests/golden_support.py`). `GOLDEN_UPDATE=1` los reescribe cuando el cambio
  de comportamiento es intencional, y el diff se revisa como parte del cambio. `PLANE_PY=<ruta>` apunta el harness a otro
  `plane.py`.
- **Reloj.** Los golden no leen la hora real: `tests/plane_clock.py` la congela dentro del proceso del CLI y `Sandbox` la
  controla (`sb.advance(segundos)`; `sb.command([...])` para lanzar con `Popen`; `clock=None` usa la hora real). No
  enmascaran fechas ni horas, así que un error en las del worklog los rompe. Las pruebas en proceso sustituyen
  `clock.timestamp` con `tests/clock_support.Clock`, y las esperas por procesos reales usan `time.monotonic`. El porqué y
  las comprobaciones están en `docs/decisions/0015-reloj-central-y-reloj-congelado-en-las-pruebas.md`.
- **`tests/plane_fast.py`** ejecuta el mismo `main()` con el timeout de lectura acortado a 1 s, para las pruebas con una
  conexión retenida (`mock.patch.object(gs, "PLANE_PY", ...)`), sin añadir variables de entorno al contrato.
- **Modo sin conexión** (`test_transport`, `test_circuit`, `test_degrade`, `test_offline_reads`, `test_outbox`,
  `test_outbox_flush`, `test_outbox_sync`): el servidor falso aplica fallos con `fake.add_fault(método, regex, tipo, arg, n)`:
  responde con un código (`status`), retiene la conexión (`hang`), la corta (`drop`), aplica la escritura y corta la
  respuesta (`commit_drop`), retrasa (`delay`), alterna (`flap`) o envía bytes crudos (`raw`). `fake.store_comments`
  guarda los comentarios con su `external_id` (409 si se repite), `fake.close()` / `reopen()` simulan una conexión
  rechazada y `Sandbox.write_circuit()` fija el estado del circuito. Los procesos concurrentes y los interrumpidos se
  prueban con procesos reales.
- **Estructura y contrato:** `test_structure.py` guarda las reglas estructurales descritas arriba; `test_cli_tree.py` fija
  el árbol exacto (y su orden), que cada hoja tenga `handler` y los grupos no, y el tamaño de la ayuda global;
  `test_renamed.py`, las pistas de nombres retirados; `test_json_flag.py`, las posiciones válidas de `--json`; y
  `test_docs.py`, los documentos de `docs/`; `test_architecture.py`, las funciones de aptitud F1-F15 del RFC 0021
  (capas y dependencias permitidas, vocabulario frente a la [decisión 0025](docs/decisions/0025-contrato-json-de-lectura.md), cobertura y notas derivadas,
  `complete` frente a los avisos) con un trinquete: `CURRENT_PHASE` avanza al cerrar cada fase del plan y una función de una fase cerrada no puede seguir saltada.
  `fake.extra_headers` añade cabeceras (`X-RateLimit-*`) a las respuestas normales del servidor falso.
- Los demás archivos prueban unidades (propuestas, sesiones, flujo, relevo, Markdown) importando `plane_cli` y
  sustituyendo `config.CACHE_DIR` y `clock.timestamp`.

## Qué no romper

- **`--help`**: global y por subcomando, idéntico y sin variables de entorno. El nombre de uso sale de `sys.argv[0]`
  (`plane.py`).
- **Orden de los subcomandos**: es el orden de `COMMANDS`; argparse lo refleja en `--help`.
- **Orden de arranque**: consultar `renamed.suggestion()` (código 2), parsear argumentos, luego validar el entorno (`PLANE_BASE_URL`, `PLANE_API_KEY`; falta de alguna
  termina con código 1, incluso en comandos que no llaman a la API) y solo entonces abrir la base de datos.
- **Nombre y ruta de `scripts/plane.py`**: el wrapper `plane-tracker` y `SKILL.md` apuntan a él, y su `sys.path` usa
  `os.path.realpath(__file__)` para resolver el symlink del skill.
- **Tests con `HOME` aislado**: ningún test escribe en `~/.cache/plane` ni habla con un Plane real; las rutas se
  desvían con `config.CACHE_DIR` o con `HOME` temporal en el subproceso.
- **Formatos de salida**: textos, JSON y códigos de salida son contrato para agentes y scripts.
- **Arranque rápido**: todo el código fuera de `plane.py` se cachea como `.pyc`; evita imports pesados o trabajo a nivel
  de módulo.

## Propuestas pendientes

Lo acordado que aún no está implementado vive en `docs/` (defectos, RFC y decisiones, con su estado en la cabecera);
`docs/INDEX.md` lo lista y marca explícitamente qué no existe en el código. Convenciones: `docs/README.md`.
