# Contrato JSON `plane-tracker/1`

Parte de [0021](./README.md) (versión 2). Lo que un agente puede asumir de cualquier salida `--json`. Los nombres definitivos viven en `vocabulary.py`; este documento es su especificación y una prueba (F4) comprueba que no se desincronizan. En la fase 0 se promueve a una decisión estable en `docs/decisions/` (este RFC cambia de estado; el contrato no debe depender de él).

## Sobre de lectura

```json
{
  "schema": "plane-tracker/1",
  "view": "list",
  "scope": {
    "projects": ["PRJ"],
    "ticket_person": {"relation": "assigned", "actor": "<uuid>"},
    "state": "open",
    "text": "formulario",
    "order": "rank,-sequence",
    "limit": 20
  },
  "total": 3,
  "count": 3,
  "results": [ { "...": "campos del vocabulario" } ],
  "summary": null,
  "coverage": {
    "source": "cache",
    "as_of": "2026-11-02T12:00:00Z",
    "age_s": 60,
    "stale": false,
    "complete": null,
    "unavailable": [],
    "detail": {"text_fields": ["title", "labels"], "history": {"verified": 2, "total": 3}}
  },
  "notes": [ {"code": "history_partial", "text": "Historial de asignación verificado en 2 de 3 tickets.", "hint": "plane-tracker sync --history"} ]
}
```

| Clave | Tipo | Regla |
| :--- | :--- | :--- |
| `schema` | cadena | `plane-tracker/<n>`; un cambio incompatible sube `<n>` y exige una decisión. |
| `view` | cadena | `list`, `report time`, `report flow`, `get`, `labels`, `projects`, ... (ver el arbol: qué comandos usan el sobre). |
| `scope` | objeto | el alcance **resuelto**: solo las dimensiones que la vista acepta. **Opcional**: `get` no lo lleva (su alcance es un ticket, en `results`). |
| `total` / `count` | entero | `total` antes del límite; `count` = `len(results)`. Sin límite (reportes) `count == total`. |
| `results` | lista | filas con **solo** campos del vocabulario de su familia. |
| `summary` | objeto o null | agregados que no son filas; mismos nombres que el vocabulario. |
| `coverage` | objeto | obligatorio. `complete`: `true`, `false` o `null` (**no verificado**, nunca equivale a completo). Regla de cálculo por vista en [`modelo-de-consulta.md`](./modelo-de-consulta.md). |
| `notes` | lista | `{code, text, hint?}`; el agente ramifica por `code`. **Derivadas de la cobertura** (`notes_from`) más las propias de la vista (`extra_notes`). Orden: severidad y luego código. |

Serialización: `ensure_ascii=False`, claves ordenadas, separadores compactos (compacto frente a indentado: README, decisión 11, con la medición hecha: el indentado cuesta +36 %). Mismo estado, reloj y zona horaria dan bytes idénticos.

**Notas informativas** (`info`) solo salen con `--verbose`; las de aviso (`warn`) siempre y llevan `hint` (el remedio como comando). Lo que ya va en `notes`/`coverage` **no se repite por stderr** en modo `--json`.

## Vocabulario por familia

Un nombre por concepto, en inglés y minúsculas, igual en todas las vistas. La definición mecánica (tipos, obligatorio u opcional) está en `vocabulary.py`; una clave fuera de su familia hace fallar la validación (F3).

### Ticket (`list`, `get`, `report agenda`)

| Campo | Tipo | Significado | Sustituye a |
| :--- | :--- | :--- | :--- |
| `ticket` | cadena | etiqueta `PRJ-12` | `ticket_id`, `issue`, `issue_id` (como etiqueta) |
| `uuid` | cadena | UUID del ticket; presente siempre en `get`, ausente en listas (se obtiene con `get`) | `id` |
| `title` | cadena | título | `name` |
| `state` | cadena | **nombre** del estado (`unknown` si la caché no lo conoce) | `state_name`; el UUID deja de exponerse |
| `state_group` | cadena | `backlog`, `unstarted`, `started`, `completed`, `cancelled`; `triage` puede aparecer (la API tiene `is_triage`) | |
| `priority` | cadena | `urgent`, `high`, `medium`, `low`, `none` | |
| `project` | cadena | identificador del proyecto | `project_id` |
| `assignees` | lista | `{id, name}` asignados ahora | |
| `created_by` | cadena | UUID del creador | |
| `labels` | lista | nombres de etiqueta | UUID de etiqueta |
| `start_date`, `target_date` | fecha o null | | `due_date` |
| `created_at`, `completed_at`, `plane_updated_at` | ISO UTC | | |
| `reasons` | lista | por qué entra en una selección de persona | |
| `assignment_events` | lista | `{at, kind, user_id, user_name}` medidos | |

**Filas breves** (propuesta, README decisión 11): `ticket`, `title`, `state`, `state_group`, `project`, sin UUID (`created_by`, `assignees[].id`) ni etiquetas ni fechas. Medidas: 336 tokens frente a 726 del sobre completo para 5 resultados; pensadas para el Momento Cero.

`get` añade `description`, `comments` (`{id, author, created_at, text}`), `links` y `attachments`; no lleva `scope`.

### Registro de horas (`report time`, `worklog check`)

| Campo | Significado | Sustituye a |
| :--- | :--- | :--- |
| `ticket`, `project`, `date`, `start_time`, `end_time`, `minutes` | qué, cuándo y cuánto | `ticket_id`, `project_id`, `duration_minutes` |
| `track`, `capacity`, `phase`, `role`, `worker_type`, `notes` | clasificación | `capacity_bucket` |
| `author` | UUID de quien registró las horas (`null` = sin autor registrado) | `author_id` |
| `provenance` | por campo: `measured` o `default` (defecto 0022) | |

### Flujo (`report flow`)

`outcome` (`completed`, `cancelled`, `open`), `flags`, `created`, `closed`, `lead_minutes`, `cycle_active_minutes`, `cycle_gross_minutes`, `by_state_minutes`, `effort_compute_minutes`, `effort_clock_minutes`, `worklogs`, `worklogs_before_created`, `worklogs_after_closed`, `effort_clock_over_cycle`. Son los nombres vigentes (`flow_metrics.py`), que se conservan; `ticket` y `title` identifican la fila.

### Comprobación de horas (`worklog check`)

Fila: `code`, `ticket`, `comment_id`, `detail`. Códigos: `duplicate`, `orphan`, `mismatch`, `missing_local`, `pending`, `unlinked`, `no_block`, `unreachable`. Son un **espacio propio** (`check_code`), registrado en `vocabulary.py` y distinto de los códigos de nota y de error. Sobre: `summary.ok` y `summary.unreachable`.

### Catálogos (`labels`, `projects`)

`labels`: `id`, `name`, `color`. `projects`: `id`, `identifier`, `name`.

### Resumen de horas (`summary` de `report time`)

`by_day`, `by_project`, `by_capacity` (cada uno lista de `{key, minutes}`), `effort_clock_minutes`, `effort_compute_minutes`; lo no medido por defecto va en `by_capacity` bajo la clave `undeclared`, nunca sumado a `deep_work`.

## Registro de códigos de nota

Severidad (`info`, `warn`), origen y remedio. Agregar uno exige añadirlo aquí y en `vocabulary.py` (F4). Los que tienen origen "cobertura" se **derivan** automáticamente.

| Código | Sev. | Origen | Cuándo | Remedio (`hint`) |
| :--- | :---: | :--- | :--- | :--- |
| `truncated` | info | resultado | `count < total` | subir `--limit` o acotar el alcance |
| `cache_stale` | warn | cobertura | se sirvió vencido porque Plane no respondió | reintentar con red o `--refresh` |
| `source_unavailable` | warn | cobertura | proyectos sin datos ni caché | conectar y `--refresh` |
| `source_forbidden` | warn | cobertura | proyectos a los que el usuario no tiene acceso (403) | revisar la membresía; se omiten |
| `rate_budget_exhausted` | warn | cobertura | se detuvo antes de agotar el límite de tasa; resultado parcial | reintentar más tarde o `sync` |
| `legacy_cache` | warn | cobertura | tickets sin datos de asignación (caché anterior) | conectar para renovarla |
| `assignment_snapshot` | info | cobertura | la asignación es la de la última sincronización | `--refresh` |
| `history_partial` | warn | cobertura | historial de asignación verificado en `a` de `b` | `sync --history` |
| `hours_local_only` | warn | cobertura | las horas salen solo de la base local de esta máquina | `report --refresh`; defecto 0017 |
| `hours_unsigned` | warn | vista | registros de horas sin autor registrado | `report --refresh` |
| `hours_defaulted` | warn | vista | horas con campos por defecto no medidos (defecto 0022) | corregir el comentario o sincronizar de nuevo |
| `single_project` | info | alcance | alcance de un solo proyecto | `--all-projects` |
| `cache_capped` | warn | cobertura | el proyecto supera el máximo sincronizable | acotar el alcance |
| `pending_unpublished` | warn | vista | comentarios en cola sin publicar que afectan el resultado | `outbox flush` |
| `text_looks_like_id` | info | vista | el texto parece un ticket (`PRJ-12`) | `plane-tracker get PRJ-12` |
| `internal` | warn | envelope | deriva del sobre detectada en producción | informar el defecto |

## Sobre de error

En `--json` los errores salen por **stdout** como objeto y con el código de salida correspondiente; en texto, mensaje y pista por stderr.

```json
{"schema": "plane-tracker/1", "status": "error", "code": "unknown_project",
 "message": "Proyecto 'XYZ' no encontrado.", "hint": "Opciones: PRJ, OPS. Usa -p PRJ.", "exit": 1}
```

| Código | Salida | Cuándo |
| :--- | :---: | :--- |
| `usage` | 2 | argparse, nombre retirado, verbo ausente o flag no soportado por la vista (`renamed.py`) |
| `unknown_project`, `unknown_state`, `unknown_label` | 1 | valor inexistente en el workspace |
| `actor_unknown` | 1 | filtro de persona sin `PLANE_ACTOR_UUID` ni `PLANE_USERNAME` |
| `bad_period`, `bad_date` | 1 | fecha mal formada o rango invertido |
| `not_found` | 1 | ticket o recurso inexistente |
| `duplicate` | 1 | `create` con título repetido reciente |
| `queue_full` | 1 | límite de la cola de salida |
| `env_missing` | 1 | falta una variable de entorno obligatoria |
| `refused` | 1 | operación destructiva rechazada por seguridad (`delete`) |
| `http_error` | 1 | error HTTP definitivo (`detail.status`) |
| `plane_unavailable` | 3 | Plane no responde y no hay alternativa local |
| `no_cache` | 3 | sin Plane y sin caché local |

Tabla fija de salida: **0** éxito (o comentario encolado); **1** error definitivo o de validación; **2** uso; **3** Plane no disponible. Un error de uso de argparse también produce el sobre en `--json` (parser propio con `allow_abbrev=False`).

## Sobre de escritura

```json
{"schema": "plane-tracker/1", "status": "ok", "action": "update", "ticket": "PRJ-12", "uuid": "<uuid>"}
```
Los mismos nombres que las lecturas; `status` es `ok`, `queued` (comentario encolado) o `error`.

## Evolución

- Tras declarar `plane-tracker/1` estable, solo se **añaden** campos y códigos; renombrar o quitar sube la versión.
- Todo cambio del vocabulario pasa por una decisión, actualiza este documento y regenera los golden con revisión manual.
