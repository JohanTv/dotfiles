"""Paquete de la CLI plane-tracker (punto de entrada: scripts/plane.py -> cli.main).

Capas (cada una solo importa de las anteriores; los cmd_* no se importan entre sí):
  1. config, clock, vocabulary, errors
                   rutas de caché y variables de entorno; reloj central (única fuente de la hora real); vocabulario cerrado y error de comando
                   (datos y excepciones puros: vocabulary no importa nada del paquete y errors solo importa vocabulary)
  2. db, circuit, api   SQLite local, circuito de fallo rápido y cliente HTTP de Plane
  3. mdhtml, cache, resolve, timeutil, coverage, envelope, store_worklogs, scope, scope_flags, freshness, store_issues, store_transitions, query_time, query_flow, query_check, render_time, render_flow, render_check, query_issues, query_get, query_catalogs, query_misc, render_issues, render_get, render_catalogs, render_misc, views, output, worklog_sync, worklog, outbox, outbox_flush, create_guard, proposal_store, proposals, flow, attachments, renamed
                   lógica reutilizable (sin parsers ni argparse)
  4. cmd_*         un módulo por familia de comandos: register_<comando>(sub) + cmd_<comando>(...)
  5. cli           parser raíz, COMMANDS (árbol ordenado de comandos y grupos) y main()

Módulos:
  config          CACHE_DIR, db_file(), request_log(), proposal_file(), get_env_or_fail()
  clock           timestamp(), now(), local_now(), local_today(): toda lectura de la hora real pasa por aquí
  vocabulary      contrato `plane-tracker/1` como datos: familias de campos, registros de notas, errores y códigos de comprobación
  errors          CliError(code, message, hint, exit_code, detail): error con código registrado
  db              conexión SQLite (WAL) y esquema
  circuit         circuito de fallo rápido entre procesos y PlaneUnavailable
  api             api_request(): clasificación de fallos, reintentos acotados, circuito y registro de latencia; rate_limit() con el presupuesto de tasa
  mdhtml          Markdown -> HTML de Plane
  cache           stale-while-error: aviso de antigüedad, sync de tickets, snapshots de `get` y lecturas locales
  resolve         proyectos, tickets, estados, etiquetas y usuario activo (con caché)
  timeutil        horarios y fusión de intervalos (Klee) para los reportes; age_text() e iso_utc()
  coverage        Coverage, Result y la regla de `complete` por vista; las notas se derivan de la cobertura
  envelope        sobre `plane-tracker/1`: build(), validate(), validate_error(), validate_write(), dumps()
  worklog         metadata oculta de los comentarios, upsert local y check_worklogs()
  outbox          cola de salida de `comment add`: guardado previo, reclamo atómico, entrega idempotente, list y drop
  outbox_flush    publicación de la cola (`outbox flush`)
  create_guard    guarda de duplicados de `create` (título reciente, envíos sin confirmar)
  worklog_sync    sincroniza worklogs de los comentarios de Plane a SQLite (proyectos accesibles, marca por proyecto y periodo, sin valores inventados)
  store_worklogs  proyectos accesibles y estado de verificación de las horas por proyecto y periodo (solo lectura)
  proposal_store  last_proposal.json con exclusión entre procesos
  proposals       medición de sesión y propuestas de duración (también --split)
  flow            lead/cycle time y esfuerzo de un ticket (`get --history`) y lectura incremental de sus transiciones
  renamed         pistas de error para nombres retirados y verbos ausentes
  attachments     subida, borrado y listado de adjuntos; `attachment add|list|delete|replace`
  cmd_comment     `comment add`
  cmd_comment_ops `comment edit`, `comment delete`, `worklog propose`
  cmd_tickets_write `create`, `update`, `link add`
  scope           Scope y resolve_scope(): alcance validado y puro contra catálogos ya cargados (CliError con pista)
  scope_flags     flags compartidos de las vistas, solo los de sus dimensiones y controles
  freshness       Env, catalogs(), ensure(), ensure_get(), ensure_catalog(), fetch_attachments(), resolve_identity(): única vía a la red de las vistas (solo GET, por proyecto, con 403 como cobertura)
  store_issues    lecturas de solo lectura de issues_cache, issue_sync y datos de personas
  query_issues    consulta de `list`: selección, orden total, filas del vocabulario y Result con cobertura
  query_get       consulta de `get`: fila ticket_detail desde la fuente adquirida y los nombres locales
  query_catalogs  consultas de `labels` y `projects`
  query_misc      consultas de `whoami`, `attachment list` y `outbox list`
  render_issues   texto de `list` a partir del sobre
  render_get      texto de `get` a partir del sobre (flujo y comentarios incluidos)
  render_catalogs texto de `labels` y `projects`
  render_misc     texto de `whoami`, `attachment list` y `outbox list`
  output          emit(): el sobre en --json o su render en texto
  views           View y VIEWS: registro de vistas de lectura (list, get, labels, projects, whoami, attachment list, outbox list)
  cmd_read        `get`, `list`, `labels`, `projects`, `whoami` (orquestan catálogos, frescura, consulta, sobre y salida)
  query_time      consulta de `report time` (horas del autor, resumen por día, proyecto y balde)
  query_flow      consulta de `report flow` con lo almacenado (funciona sin conexión)
  query_check     consulta de `worklog check` (transforma la auditoría de red)
  render_time     texto de `report time` desde el sobre
  render_flow     texto de `report flow` desde el sobre
  render_check    texto de `worklog check` desde el sobre
  store_transitions  tickets del periodo, estados y transiciones para `report flow` (solo lectura)
  cmd_report      `report time`, `report flow`, `worklog check`
  cmd_sync        `sync` (tickets y horas, o `--history`): solo GET, escribe solo la base local
  cmd_outbox      `outbox list|flush|drop`
  cmd_ops         `health`, `focus set|clear|status`, `handoff`
  cli             parser raíz, grupos de verbos y despacho
"""
