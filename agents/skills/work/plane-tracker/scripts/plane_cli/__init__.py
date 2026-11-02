"""Paquete de la CLI plane-tracker (punto de entrada: scripts/plane.py -> cli.main).

Capas (cada una solo importa de las anteriores; los cmd_* no se importan entre sí):
  1. config, clock, vocabulary, errors
                   rutas de caché y variables de entorno; reloj central (única fuente de la hora real); vocabulario cerrado y error de comando
                   (datos y excepciones puros: vocabulary no importa nada del paquete y errors solo importa vocabulary)
  2. db, circuit, api   SQLite local, circuito de fallo rápido y cliente HTTP de Plane
  3. mdhtml, cache, resolve, timeutil, coverage, envelope, scope, scope_flags, freshness, store_issues, query_issues, render_issues, views, history_sweep, worklog, outbox, outbox_flush, create_guard, sync, proposal_store, proposals, flow, attachments, renamed
                   lógica reutilizable (sin parsers ni argparse)
  4. cmd_*         un módulo por familia de comandos: register_<comando>(sub) + cmd_<comando>(...)
  5. cli           parser raíz, COMMANDS (árbol ordenado de comandos y grupos) y main()

Módulos:
  config          CACHE_DIR, db_file(), request_log(), proposal_file(), get_env_or_fail()
  clock           timestamp(), now(), local_now(), local_today(): toda lectura de la hora real pasa por aquí
  vocabulary      contrato `plane-tracker/1` como datos: familias de campos, registros de notas, errores y códigos de comprobación
  errors          CliError(code, message, hint, exit_code, detail): error con código registrado (aún no sustituye a los sys.exit)
  db              conexión SQLite (WAL) y esquema
  circuit         circuito de fallo rápido entre procesos y PlaneUnavailable
  api             api_request(): clasificación de fallos, reintentos acotados, circuito y registro de latencia; rate_limit() con el presupuesto de tasa
  mdhtml          Markdown -> HTML de Plane
  cache           stale-while-error: aviso de antigüedad, sync de tickets, snapshots de `get` y lecturas locales
  resolve         proyectos, tickets, estados, etiquetas y usuario activo (con caché)
  timeutil        horarios y fusión de intervalos (Klee) para los reportes; age_text() e iso_utc()
  coverage        Coverage, Result y la regla de `complete` por vista; las notas se derivan de la cobertura (aún sin consumidores)
  envelope        sobre `plane-tracker/1`: build(), validate(), dumps() (aún sin consumidores)
  worklog         metadata oculta de los comentarios, upsert local y check_worklogs()
  outbox          cola de salida de `comment add`: guardado previo, reclamo atómico, entrega idempotente, list y drop
  outbox_flush    publicación de la cola (`outbox flush`)
  create_guard    guarda de duplicados de `create` (título reciente, envíos sin confirmar)
  sync            sincroniza worklogs de los comentarios de Plane a SQLite
  proposal_store  last_proposal.json con exclusión entre procesos
  proposals       medición de sesión y propuestas de duración (también --split)
  flow            lead/cycle time y esfuerzo por ticket; `report flow`
  renamed         pistas de error para nombres retirados y verbos ausentes
  attachments     subida, borrado y listado de adjuntos; `attachment add|list|delete|replace`
  cmd_comment     `comment add`
  cmd_comment_ops `comment edit`, `comment delete`, `worklog propose`
  cmd_tickets_write `create`, `update`, `link add`
  scope           Scope y resolve_scope(): alcance validado y puro contra catálogos ya cargados (CliError con pista)
  scope_flags     flags compartidos de las vistas, solo los de sus dimensiones y controles
  freshness       Env, catalogs() y ensure(): única vía a la red de las vistas (solo GET, por proyecto, con 403 como cobertura)
  store_issues    lecturas de solo lectura de issues_cache, issue_sync y datos de personas
  query_issues    consulta de `list`: selección, orden total, filas del vocabulario y Result con cobertura
  render_issues   texto de `list` a partir del sobre
  views           View y VIEWS: registro de vistas de lectura
  history_sweep   barrido de `list --refresh-history` (se retira en la fase 6)
  cmd_read        `get`, `list`, `search`, `labels`, `projects`, `whoami`
  cmd_report      `report`, `worklog check`
  cmd_outbox      `outbox list|flush|drop`
  cmd_ops         `health`, `focus set|clear|status`, `handoff`
  cli             parser raíz, grupos de verbos y despacho
"""
