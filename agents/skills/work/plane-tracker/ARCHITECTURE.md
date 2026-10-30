# Arquitectura del CLI `plane-tracker`

Documento para quien modifica el código. El uso del CLI (comandos, flags, protocolo de bitácoras) está en `SKILL.md`.

El CLI es de solo biblioteca estándar de Python (3.10+). `scripts/plane.py` es el punto de entrada: inserta su propio
directorio real en `sys.path`, importa `plane_cli.cli.main` y lo ejecuta. El código vive en el paquete plano
`scripts/plane_cli/`; `session_clock.py` y `flow_metrics.py` son módulos independientes de `scripts/` (lectura de
transcripts de agentes y cálculo de flujo) que el paquete importa como módulos de primer nivel.

## Mapa de módulos

Las líneas son aproximadas; el tope duro por archivo es 450.

| Módulo | Líneas | Responsabilidad |
|---|---|---|
| `plane.py` | 16 | Punto de entrada: ajusta `sys.path` y llama a `cli.main()`. |
| `plane_cli/__init__.py` | 30 | Docstring con el mapa de capas y módulos. |
| `plane_cli/config.py` | 75 | `CACHE_DIR`, rutas derivadas (`db_file()`, `request_log()`, `proposal_file()`), reloj `now()`, `local_midnight_utc()`, `positive_int()`, carga de `~/.zshrc.local` y `get_env_or_fail()`. |
| `plane_cli/db.py` | 180 | Conexión SQLite (WAL), `ensure_columns()` y esquema (`init_db()`). |
| `plane_cli/api.py` | 75 | `api_request()` con reintento ante 429 y `log_request()` (JSONL de latencias). |
| `plane_cli/mdhtml.py` | 150 | `markdown_to_html()`: subconjunto de Markdown que renderiza Plane CE. |
| `plane_cli/resolve.py` | 285 | Proyectos, tickets, estados, etiquetas y usuario activo contra Plane, con caché SQLite; `detect_ticket_from_git()`. |
| `plane_cli/timeutil.py` | 215 | Aritmética de horarios, unión de intervalos (medida de Klee), fusión diaria de worklogs y `render_day_block()`. |
| `plane_cli/worklog.py` | 220 | Bloque oculto `PLANE_WORKLOG_METADATA`, `upsert_worklog()`, `check_worklogs()`, `reject_placeholders()` y `PLACEHOLDER`. |
| `plane_cli/sync.py` | 145 | `sync_remote_worklogs()`: comentarios de Plane a SQLite. |
| `plane_cli/proposal_store.py` | 100 | `last_proposal.json`: guardar, leer, consumir y bloquear entre procesos. |
| `plane_cli/proposals.py` | 290 | Medición de la sesión del agente, ventanas, `build_proposal()`, `build_split()` y su impresión. |
| `plane_cli/flow.py` | 210 | Lead/cycle time y esfuerzo por ticket, y el comando `report --flow`. |
| `plane_cli/attachments.py` | 135 | Subida firmada, borrado y listado de adjuntos; comandos `attach` y `attachments`. |
| `plane_cli/cmd_comment.py` | 235 | Comando `comment`. |
| `plane_cli/cmd_comment_ops.py` | 195 | Comandos `comment-edit`, `comment-delete` y `propose-duration`. |
| `plane_cli/cmd_tickets_write.py` | 270 | Comandos `create`, `update` y `link`. |
| `plane_cli/cmd_read.py` | 405 | Comandos `get`, `list`, `search`, `labels`, `projects` y `whoami`. |
| `plane_cli/cmd_report.py` | 220 | Comando `report` y `report --check`. |
| `plane_cli/cmd_ops.py` | 235 | Comandos `health`, `focus` y `handoff`, con sus ayudantes de git. |
| `plane_cli/cli.py` | 65 | Parser raíz, `COMMAND_REGISTRARS` (lista ordenada) y `main()`. |

## Capas y regla de dependencias

1. `config`: no importa nada del paquete.
2. `db`, `api`: dependen de `config`.
3. Lógica reutilizable (`mdhtml`, `resolve`, `timeutil`, `worklog`, `sync`, `proposal_store`, `proposals`, `flow`,
   `attachments`): importan de capas 1 y 2 y entre sí en una sola dirección. Salvo `attachments` (`attach`,
   `attachments`) y `flow` (`report --flow`), que además contienen el comando que los usa, no definen parsers.
4. `cmd_*`: importan de las capas 1 a 3; **nunca** se importan entre sí ni importan `cli`.
5. `cli`: importa los `cmd_*` y `attachments` para registrar los subcomandos.

Ninguna biblioteca importa un `cmd_*`. No hay ciclos de import. `tests/test_structure.py` lo verifica con un análisis del
AST, además de los nombres globales no definidos, el tamaño de archivos (450 líneas) y de funciones (150 líneas) y que
ningún módulo se llame como uno de la biblioteca estándar (el directorio de scripts va primero en `sys.path`, así que
un `http.py` o `types.py` sombrearía el módulo estándar).

Los módulos se importan siempre por nombre explícito (`from plane_cli.resolve import resolve_issue`), nunca con `*`.

## Convenciones

- **Reloj y rutas solo por `config`.** El código lee `config.now()` y `config.CACHE_DIR` / `db_file()` /
  `request_log()` / `proposal_file()` por atributo del módulo en cada llamada; nunca `from plane_cli.config import now`.
  Así un test sustituye `config.now` o `config.CACHE_DIR` y el cambio llega a todos los módulos.
- **Idioma:** mensajes de usuario, comentarios y documentación en español; flags e identificadores internos en inglés.
- **Comentarios:** concisos y agnósticos; explican el porqué de una restricción vigente, no la historia del cambio.
- **Docstring de cabecera** en cada módulo: responsabilidad, qué expone y qué no hace.
- **Firma de los comandos:** `cmd_x(args, conn, base_url, api_key, workspace, default_project_id)`, aunque el comando
  no use todos los parámetros. `cli.main()` los llama como `args.handler(...)`.
- **Registro de subcomandos:** cada comando tiene `register_<comando>(sub)` (con guion bajo en lugar de guion) que define
  su parser y hace `set_defaults(handler=cmd_<comando>)`.

## Agregar un comando

1. Crear (o ampliar) un `plane_cli/cmd_x.py` con `cmd_nombre(args, conn, base_url, api_key, workspace, default_project_id)`
   y `register_nombre(sub)`, que añade el parser con sus flags y termina en `set_defaults(handler=cmd_nombre)`. Si el
   archivo supera las 450 líneas, o la lógica es reutilizable por otros comandos, esa lógica va a un módulo de la capa 3.
2. Añadir `cmd_x.register_nombre` a `COMMAND_REGISTRARS` en `cli.py`, en la posición en que debe aparecer en `--help`.
3. Añadir los casos al golden: el `--help` del subcomando (lista `SUBCOMMANDS` en `tests/test_golden.py`) y un escenario
   con su salida, peticiones al servidor falso y filas locales. Generarlo con `GOLDEN_UPDATE=1` y revisar el diff a mano.
4. Documentar el comando en `SKILL.md` (sección de comandos disponibles).

## Tests

Desde el directorio del skill:

```bash
python3 -m unittest discover -s tests
```

- `test_golden.py` ejecuta el CLI por subproceso contra un servidor Plane falso (`http.server` en 127.0.0.1) con `HOME`
  temporal, `TZ=UTC` y credenciales ficticias, y compara salida, código de salida, peticiones enviadas y filas locales
  con `tests/golden/*.txt`. Lo no determinista (fechas de hoy, ids de reparto, latencias) se normaliza en
  `tests/golden_support.py`.
- `GOLDEN_UPDATE=1` reescribe los golden; solo se usa cuando el cambio de comportamiento es intencional, y el diff se
  revisa como parte del cambio. `PLANE_PY=<ruta>` apunta el harness a otro `plane.py`.
- `test_structure.py` guarda las reglas estructurales descritas arriba.
- Los demás archivos prueban unidades (propuestas, sesiones, flujo, relevo, Markdown) importando los módulos de
  `plane_cli` directamente y sustituyendo `config.CACHE_DIR` / `config.now`.

## Qué no romper

- **`--help`**: global y por subcomando, idéntico y sin variables de entorno. El nombre de uso sale de `sys.argv[0]`
  (`plane.py`).
- **Orden de los subcomandos**: es el orden de `COMMAND_REGISTRARS`; argparse lo refleja en `--help`.
- **Orden de arranque**: parsear argumentos, luego validar el entorno (`PLANE_BASE_URL`, `PLANE_API_KEY`; falta de alguna
  termina con código 1, incluso en comandos que no llaman a la API) y solo entonces abrir la base de datos.
- **Nombre y ruta de `scripts/plane.py`**: el wrapper `plane-tracker` y `SKILL.md` apuntan a él, y su `sys.path` usa
  `os.path.realpath(__file__)` para resolver el symlink del skill.
- **Tests con `HOME` aislado**: ningún test escribe en `~/.cache/plane` ni habla con un Plane real; las rutas se
  desvían con `config.CACHE_DIR` o con `HOME` temporal en el subproceso.
- **Formatos de salida**: textos, JSON y códigos de salida son contrato para agentes y scripts.
- **Arranque rápido**: todo el código fuera de `plane.py` se cachea como `.pyc`; evita imports pesados o trabajo a nivel
  de módulo.
