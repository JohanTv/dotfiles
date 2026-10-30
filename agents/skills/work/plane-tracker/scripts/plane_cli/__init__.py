"""Paquete de la CLI plane-tracker (punto de entrada: scripts/plane.py -> cli.main).

Capas (cada una solo importa de las anteriores; los cmd_* no se importan entre sí):
  1. config        rutas de caché, reloj, variables de entorno
  2. db, api       SQLite local y cliente HTTP de Plane
  3. mdhtml, resolve, timeutil, worklog, sync, proposal_store, proposals, flow, attachments, renamed
                   lógica reutilizable (sin parsers ni argparse)
  4. cmd_*         un módulo por familia de comandos: register_<comando>(sub) + cmd_<comando>(...)
  5. cli           parser raíz, COMMANDS (árbol ordenado de comandos y grupos) y main()

Módulos:
  config          CACHE_DIR, db_file(), request_log(), proposal_file(), now(), get_env_or_fail()
  db              conexión SQLite (WAL) y esquema
  api             api_request() con reintento ante 429 y registro de latencia
  mdhtml          Markdown -> HTML de Plane
  resolve         proyectos, tickets, estados, etiquetas y usuario activo (con caché)
  timeutil        horarios y fusión de intervalos (Klee) para los reportes
  worklog         metadata oculta de los comentarios, upsert local y check_worklogs()
  sync            sincroniza worklogs de los comentarios de Plane a SQLite
  proposal_store  last_proposal.json con exclusión entre procesos
  proposals       medición de sesión y propuestas de duración (también --split)
  flow            lead/cycle time y esfuerzo por ticket; `report flow`
  renamed         pistas de error para nombres retirados y verbos ausentes
  attachments     subida, borrado y listado de adjuntos; `attachment add|list|delete|replace`
  cmd_comment     `comment add`
  cmd_comment_ops `comment edit`, `comment delete`, `worklog propose`
  cmd_tickets_write `create`, `update`, `link add`
  cmd_read        `get`, `list`, `search`, `labels`, `projects`, `whoami`
  cmd_report      `report`, `worklog check`
  cmd_ops         `health`, `focus set|clear|status`, `handoff`
  cli             parser raíz, grupos de verbos y despacho
"""
