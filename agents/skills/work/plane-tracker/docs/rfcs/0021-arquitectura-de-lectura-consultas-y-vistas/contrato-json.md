# Contrato JSON `plane-tracker/1`

Parte de [0021](./README.md). Lo que un agente puede asumir de cualquier salida `--json`. Los nombres definitivos viven en `vocabulary.py`; este documento es su especificación y una prueba (F4) comprueba que no se desincronizan.

## Sobre de lectura

```json
{
  "schema": "plane-tracker/1",
  "view": "list",
  "scope": {
    "projects": ["PRJ"],
    "person": {"relation": "assigned", "actor": "<uuid>"},
    "period": null,
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
    "detail": {"text_fields": ["title", "labels"], "history": {"verified": 2, "total": 3}},
    "unavailable": []
  },
  "notes": [ {"code": "history_partial", "text": "Historial de asignación verificado en 2 de 3 tickets."} ]
}
```

| Clave | Tipo | Regla |
| :--- | :--- | :--- |
| `schema` | cadena | `plane-tracker/<n>`; un cambio incompatible sube `<n>` y exige una decisión en `docs/decisions/`. |
| `view` | cadena | nombre de la vista (`list`, `report time`, `report flow`, `report agenda`, `get`, ...). |
| `scope` | objeto | el alcance **resuelto** (no el pedido): proyectos como identificadores, estado efectivo, orden y límite. Las dimensiones que la vista no acepta no aparecen. |
| `total` / `count` | entero | `total` antes del límite, `count` = `len(results)`. `count < total` implica la nota `truncated`. |
| `results` | lista | filas con **solo** campos del vocabulario. |
| `summary` | objeto o null | agregados que no son filas (p. ej. horas por día y por proyecto, medianas de flujo). Mismos nombres de campo que el vocabulario. |
| `coverage` | objeto | obligatorio. `complete`: `true`, `false` o `null` (**no verificado**; nunca equivale a completo). |
| `notes` | lista | `{code, text}`; el agente ramifica por `code`, el `text` es para humanos. Orden: severidad y luego código. |

Serialización: `ensure_ascii=False`, claves ordenadas, separadores compactos. Mismo estado y mismo reloj dan bytes idénticos.

## Vocabulario de campos (resultados)

Un nombre por concepto, en inglés y en minúsculas, igual en todas las vistas.

| Campo | Tipo | Significado | Nombres que sustituye |
| :--- | :--- | :--- | :--- |
| `ticket` | cadena | `PRJ-12` | `ticket_id`, `issue`, `issue_id` (como etiqueta) |
| `uuid` | cadena | UUID del ticket; solo si hace falta | `id`, `issue_id` (como UUID) |
| `title` | cadena | título | `name` |
| `state` | cadena | **nombre** del estado | `state_name`; (el UUID deja de exponerse) |
| `state_group` | cadena | `backlog`, `unstarted`, `started`, `completed`, `cancelled` | |
| `priority` | cadena | `urgent`, `high`, `medium`, `low`, `none` | |
| `project` | cadena | identificador del proyecto | `project_id` (en horas), `scope` |
| `assignees` | lista de `{id, name}` | asignados ahora | |
| `created_by` | cadena | UUID del creador | |
| `labels` | lista de cadenas | nombres | `labels` como UUID |
| `target_date`, `start_date` | fecha o null | | `due_date` |
| `created_at`, `completed_at`, `plane_updated_at` | ISO UTC | | |
| `reasons` | lista | por qué entra en una selección de persona | |
| `assignment_events` | lista | `{at, kind, user_id, user_name}` medidos | |
| `date`, `start_time`, `end_time`, `minutes` | | registro de horas | `duration_minutes` |
| `track`, `capacity`, `worker_type`, `author` | | registro de horas | `capacity_bucket` |

La tabla completa y los tipos están en `vocabulary.py`; una clave fuera de ella hace fallar `envelope.build`.

## Registro de códigos de nota

Cada código tiene severidad (`info`, `warn`), plantilla de texto y remedio. Agregar uno exige añadirlo aquí y en `vocabulary.py` (F4).

| Código | Sev. | Cuándo | Remedio |
| :--- | :---: | :--- | :--- |
| `truncated` | info | `count < total` | subir `--limit` o acotar el alcance |
| `cache_stale` | warn | se sirvió vencido porque Plane no respondió | reintentar con red o `--refresh` |
| `source_unavailable` | warn | proyectos sin datos ni caché (`coverage.unavailable`) | conectar y `--refresh` |
| `legacy_cache` | warn | tickets sin datos de asignación (caché anterior) | conectar para renovar la caché |
| `assignment_snapshot` | info | la asignación es la de la última sincronización | `--refresh` |
| `history_partial` | warn | historial de asignación verificado en `a` de `b` | `sync --history` |
| `hours_local_only` | warn | las horas salen solo de la base local de esta máquina | `report --refresh`; ver 0017 |
| `hours_unsigned` | warn | registros de horas sin autor registrado | `report --refresh` |
| `single_project` | info | alcance de un solo proyecto | `--all-projects` |
| `cache_capped` | warn | el proyecto supera el máximo sincronizable | acotar el alcance |
| `pending_unpublished` | warn | comentarios en cola sin publicar que afectan el resultado | `outbox flush` |

## Sobre de error

En modo `--json` los errores salen por **stdout** como objeto y con el código de salida correspondiente; en modo texto, mensaje y pista por stderr.

```json
{"schema": "plane-tracker/1", "status": "error", "code": "unknown_project",
 "message": "Proyecto 'XYZ' no encontrado.", "hint": "Opciones: PRJ, OPS. Usa -p PRJ.", "exit": 1}
```

| Código de error | Salida | Cuándo |
| :--- | :---: | :--- |
| `usage` | 2 | argparse, nombre retirado o verbo ausente (`renamed.py`) |
| `unknown_project` | 1 | proyecto inexistente |
| `actor_unknown` | 1 | filtro de persona sin `PLANE_ACTOR_UUID` ni `PLANE_USERNAME` |
| `bad_period` | 1 | fecha mal formada o rango invertido |
| `not_found` | 1 | ticket o recurso inexistente |
| `refused` | 1 | operación destructiva rechazada por seguridad (p. ej. `delete`) |
| `plane_unavailable` | 3 | Plane no responde y no hay alternativa local |
| `no_cache` | 3 | sin Plane y sin caché local |

Tabla fija de salida: **0** éxito (o comentario encolado); **1** error definitivo o de validación; **2** uso; **3** Plane no disponible.

## Sobre de escritura

```json
{"schema": "plane-tracker/1", "status": "ok", "action": "update", "ticket": "PRJ-12", "uuid": "<uuid>"}
```
Los mismos nombres de campo que las lecturas; `status` es `ok`, `queued` (comentario encolado) o `error` (ver arriba).

## Evolución

- Después de declarar `plane-tracker/1` estable, solo se **añaden** campos y códigos; renombrar o quitar sube la versión.
- Todo cambio del vocabulario pasa por una decisión en `docs/decisions/`, actualiza este documento y regenera los golden con revisión manual.
- Los avisos que hoy van a stderr se **duplican** en `notes`/`coverage`; stderr sigue existiendo para humanos.
