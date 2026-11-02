"""Vocabulario cerrado del contrato de lectura `plane-tracker/1` (decisión 0025): una sola fuente de nombres.

Expone: SCHEMA, DIMENSIONS, CONTROLS, PERSON_RELATIONS, SCOPE_KEYS, ENVELOPE_KEYS, COVERAGE_SOURCES, COVERAGE_KEYS, DETAIL_KEYS,
VIEWS, FAMILIES, NESTED, BRIEF_FIELDS, SUMMARIES, REPLACES, DROPPED, NOTES, ALWAYS_SHOWN, GET_INCLUDES, GET_INCLUDES_COVERED, DERIVED_ORIGINS, ERRORS, CHECK_CODES, field_spec().
No hace: importar nada del paquete, validar sobres (eso es envelope) ni calcular cobertura (coverage). Son datos puros.
Un campo se declara como "tipo" con sufijos: `?` admite null y `!` es obligatorio (ej. "str?!"); tipos: str, int, num, bool, list, dict.
La especificación legible es docs/decisions/0025-contrato-json-de-lectura; una prueba (F4) comprueba que no se desincronizan.
"""

SCHEMA = "plane-tracker/1"

# --- Alcance -----------------------------------------------------------------------------------------------------------------------------
DIMENSIONS = frozenset({"projects", "person", "period", "state", "text"})
CONTROLS = frozenset({"limit", "refresh", "offline", "verbose", "brief"})
PERSON_RELATIONS = ("assigned", "created", "involved")
STATES = ("open", "all")
# Claves del `scope` del sobre: lo resuelto de cada dimensión (`person` se reparte en ticket_person y hours_author) más orden y límite.
SCOPE_KEYS = frozenset({"projects", "ticket_person", "hours_author", "period", "state", "text", "order", "limit", "track", "worker_type"})

# --- Sobre y cobertura -------------------------------------------------------------------------------------------------------------------
ENVELOPE_KEYS = {"schema": "str!", "view": "str!", "scope": "dict", "total": "int!", "count": "int!", "results": "list!", "summary": "dict?!",
                 "coverage": "dict!", "notes": "list!"}
COVERAGE_SOURCES = ("cache", "api", "snapshot", "local", "mixed")
COVERAGE_KEYS = {"source": "str!", "as_of": "str?!", "age_s": "int?!", "stale": "bool!", "complete": "bool?!", "unavailable": "list!", "detail": "dict!"}
# Claves conocidas de coverage.detail (por vista); las que alimentan notas derivadas están en coverage.py.
DETAIL_KEYS = frozenset({"history", "text_fields", "hours_scope", "capped", "legacy", "forbidden", "rate_budget_exhausted", "assignment_snapshot",
                         "count_mismatch", "hours_verified", "comments", "metadata_only", "include"})
NOTE_KEYS = {"code": "str!", "text": "str!", "hint": "str"}
ERROR_KEYS = {"schema": "str!", "status": "str!", "code": "str!", "message": "str!", "hint": "str", "exit": "int!", "detail": "dict"}

# --- Familias de resultado ---------------------------------------------------------------------------------------------------------------
BRIEF_FIELDS = ("ticket", "title", "state", "state_group", "project")  # filas breves de `list --brief`; también los campos obligatorios de un ticket
_TICKET = {"ticket": "str!", "uuid": "str", "title": "str!", "state": "str!", "state_group": "str!", "priority": "str", "project": "str!",
           "assignees": "list", "created_by": "str?", "labels": "list", "start_date": "str?", "target_date": "str?", "created_at": "str?",
           "completed_at": "str?", "plane_updated_at": "str?", "reasons": "list", "assignment_events": "list"}
_FLOW = {"ticket": "str!", "title": "str", "outcome": "str!", "flags": "list", "created": "str?", "closed": "str?", "lead_minutes": "num?",
         "cycle_active_minutes": "num?", "cycle_gross_minutes": "num?", "by_state_minutes": "dict", "effort_compute_minutes": "num?",
         "effort_clock_minutes": "num?", "worklogs": "int", "worklogs_before_created": "int", "worklogs_after_closed": "int",
         "effort_clock_over_cycle": "num?", "transitions": "list"}
FAMILIES = {
    "ticket": _TICKET,
    "ticket_detail": {**_TICKET, "description": "str?", "comments": "list", "links": "list", "attachments": "list",
                      "flow": "dict"},  # `get --history` anida los nombres de la familia `flow` (sin ticket ni title)
    "hours": {"ticket": "str!", "project": "str", "date": "str!", "start_time": "str!", "end_time": "str!", "minutes": "int!", "track": "str",
              "capacity": "str", "phase": "str", "role": "str", "worker_type": "str", "notes": "str", "author": "str?", "provenance": "dict"},
    "flow": _FLOW,
    "check": {"code": "str!", "ticket": "str!", "comment_id": "str?", "detail": "str"},
    "label": {"id": "str!", "name": "str!", "color": "str"},
    "whoami": {"workspace": "str!", "base_url": "str", "actor": "str?", "username": "str?", "source": "str!", "status": "str!"},
    "attachment": {"ticket": "str!", "id": "str!", "name": "str?", "size": "int?", "created_at": "str?"},
    "outbox_item": {"id": "int!", "client_id": "str!", "state": "str!", "ticket": "str!", "track": "str", "date": "str", "start_time": "str",
                    "minutes": "int?", "attempts": "int", "maybe_delivered": "bool", "last_error": "str?", "plane_comment_id": "str?",
                    "created_at": "str", "preview": "str"},
    "project": {"id": "str!", "identifier": "str!", "name": "str!"},
}
# Objetos anidados dentro de una fila: nombre del campo -> claves permitidas de cada elemento.
NESTED = {"assignees": {"id", "name"}, "assignment_events": {"at", "kind", "user_id", "user_name"}, "comments": {"id", "author", "created_at", "text"},
          "transitions": {"at", "from", "to"}, "attachments": {"id", "name", "size", "created_at"}, "links": {"id", "title", "url", "created_at"}}
# `get --include`: qué se puede pedir y qué cubre hoy (cada cubierto cuesta 1 GET). Lo demás se acepta pero solo avisa (`include_not_covered`): V37.
GET_INCLUDES = ("attachments", "links", "relations", "children")
GET_INCLUDES_COVERED = ("attachments", "links")
# Agregados (`summary`) por familia de resumen. `report time` lleva listas de {key, minutes}; `undeclared` va en by_capacity, nunca sumado a deep_work.
SUMMARIES = {
    "hours_summary": {"by_day": "list", "by_project": "list", "by_capacity": "list", "effort_clock_minutes": "int", "effort_compute_minutes": "int"},
    "flow_summary": {"tickets": "int", "completed": "int", "cancelled": "int", "open": "int", "excluded": "int", "n_lead": "int", "n_cycle": "int",
                     "median_lead_minutes": "num?", "median_cycle_minutes": "num?"},
    "check_summary": {"ok": "bool", "unreachable": "int"},
}
SUMMARY_ITEM_KEYS = {"key", "minutes"}  # elementos de by_day, by_project y by_capacity
# vista -> (familia de filas, familia de resumen o None, lleva `scope`). `get` no lleva alcance: el alcance es un ticket, en `results`.
VIEWS = {"list": ("ticket", None, True), "get": ("ticket_detail", None, False), "report time": ("hours", "hours_summary", True),
         "report flow": ("flow", "flow_summary", True), "worklog check": ("check", "check_summary", True), "labels": ("label", None, True),
         "projects": ("project", None, True), "whoami": ("whoami", None, False), "attachment list": ("attachment", None, False),
         "outbox list": ("outbox_item", None, True)}

# Nombre de hoy -> nombre del contrato (columna "Sustituye a"), por familia. Sirve para validar el vocabulario contra los JSON reales (F4).
REPLACES = {
    "ticket": {"ticket": ("ticket_id", "issue", "issue_id"), "uuid": ("id",), "title": ("name",), "state": ("state_name",),
               "project": ("project_id",), "target_date": ("due_date",), "plane_updated_at": ("updated_at",), "description": ("description_html",)},
    "hours": {"ticket": ("ticket_id",), "project": ("project_id",), "minutes": ("duration_minutes",), "capacity": ("capacity_bucket",),
              "author": ("author_id",), "provenance": ("defaulted_json",)},
    "assignment_events": {"at": ("at_utc",)},
    "outbox_item": {"minutes": ("duration_minutes",)},
    "comments": {"author": ("actor", "created_by"), "text": ("comment_html",)},
}
# Campos de hoy que el contrato no lleva y que se descartan a propósito (registrados en la revisión adversarial, V18).
DROPPED = {
    "ticket": ("sequence_id", "updated_by"),  # sequence_id ya va dentro de `ticket`
    "ticket_detail": ("total_comments", "comments_skipped", "stale", "fetched_at", "metadata_only"),
    "hours": ("issue_name", "stoppers_json", "raw_payload", "plane_comment_id", "created_at", "updated_at"),
}

# --- Notas -------------------------------------------------------------------------------------------------------------------------------
# código -> (severidad, origen, plantilla del texto o None si lo aporta la vista, remedio). Origen: cobertura, resultado y alcance se DERIVAN
# (coverage.notes_from); vista las añade la consulta (extra_notes); envelope solo lo escribe el sobre. Un aviso (warn) siempre lleva remedio.
DERIVED_ORIGINS = frozenset({"cobertura", "resultado", "alcance"})
NOTES = {
    "truncated": ("info", "resultado", "Se muestran {count} de {total} resultados.", None),
    "cache_stale": ("warn", "cobertura", "Datos locales de hace {age}; Plane no respondió.", "Reintenta con red o usa --refresh."),
    "source_unavailable": ("warn", "cobertura", "Sin datos ni caché de: {projects}.", "Conéctate y usa --refresh."),
    "source_forbidden": ("warn", "cobertura", "Sin acceso a: {projects}.", "Revisa la membresía; se omiten."),
    "rate_budget_exhausted": ("warn", "cobertura", "Se detuvo antes de agotar el límite de tasa; el resultado es parcial.",
                              "Reintenta más tarde."),
    "legacy_cache": ("warn", "cobertura", "Hay tickets sin datos de asignación (caché anterior).", "Conéctate para renovarla."),
    "assignment_snapshot": ("info", "cobertura", "La asignación es la de la última sincronización.", "Usa --refresh."),
    "history_partial": ("warn", "cobertura", "Historial de asignación verificado en {verified} de {total} tickets.", "plane-tracker sync --history"),
    "hours_local_only": ("warn", "cobertura", "Las horas salen solo de la base local de esta máquina.", "plane-tracker report time --refresh"),
    "hours_unsigned": ("warn", "vista", None, "plane-tracker report time --refresh"),
    "hours_defaulted": ("warn", "vista", None, "Corrige el comentario o sincroniza de nuevo."),
    "single_project": ("info", "alcance", "Alcance de un solo proyecto: {project}.", "Usa --all-projects."),
    "cache_capped": ("warn", "cobertura", "El proyecto supera el máximo sincronizable: {projects}.", "Acota el alcance."),
    "pending_unpublished": ("warn", "vista", None, "plane-tracker outbox flush"),
    "text_looks_like_id": ("info", "vista", None, "plane-tracker get <ticket>"),
    "include_not_covered": ("warn", "vista", None, "Por ahora get solo incluye attachments y links."),
    "internal": ("warn", "envelope", None, "Informa el defecto."),
}
SEVERITY_ORDER = ("warn", "info")  # al ordenar notas, los avisos van antes que las informativas
# Notas informativas que salen siempre, sin --verbose: lo que el agente necesita para no concluir de más (hay más resultados que los mostrados; el texto era un ticket).
ALWAYS_SHOWN = frozenset({"truncated", "text_looks_like_id"})

# --- Errores -----------------------------------------------------------------------------------------------------------------------------
# código -> código de salida. Tabla fija de salida: 0 éxito, 1 error definitivo o de validación, 2 uso, 3 Plane no disponible.
ERRORS = {"usage": 2, "unknown_project": 1, "unknown_state": 1, "unknown_label": 1, "actor_unknown": 1, "bad_period": 1, "bad_date": 1,
          "not_found": 1, "duplicate": 1, "queue_full": 1, "env_missing": 1, "refused": 1, "http_error": 1, "plane_unavailable": 3, "no_cache": 3}
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_UNAVAILABLE = 0, 1, 2, 3
# Espacio propio de `worklog check` (no se confunde con códigos de nota ni de error).
CHECK_CODES = ("duplicate", "orphan", "mismatch", "missing_local", "pending", "unlinked", "no_block", "unreachable")


def field_spec(spec):
    """'str?!' -> (tipo, admite_null, obligatorio)."""
    return spec.rstrip("?!"), "?" in spec, spec.endswith("!")
