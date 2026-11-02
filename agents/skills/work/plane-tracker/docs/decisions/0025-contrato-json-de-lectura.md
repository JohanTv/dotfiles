---
id: "0025"
title: Contrato JSON de lectura plane-tracker/1
status: aceptado
created: 2026-11-02
summary: Sobre, vocabulario por familia, registros de notas, errores y códigos de salida de las lecturas; especificación estable de vocabulary.py, promovida desde el RFC 0021.
---

# 0025 · Contrato JSON de lectura `plane-tracker/1`

Promueve [`contrato-json.md`](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/contrato-json.md) del RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) a una decisión estable, para que las pruebas de arquitectura no dependan de un documento cuyo estado cambia. Es la especificación de lo que un agente puede asumir de cualquier salida `--json`. Los nombres viven en `scripts/plane_cli/vocabulary.py` y la prueba F4 (`tests/test_architecture.py`) comprueba que los dos no se desincronizan: **cambiar uno exige cambiar el otro**.

**Estado del contrato.** Aceptado como diseño. Se declara **estable** (y la evolución pasa a ser solo aditiva) al cerrar la fase 8 del plan de migración del RFC 0021; hasta entonces el RFC sigue siendo `propuesto` y ningún documento cita el modelo como existente en el código.

## Sobre de lectura

```json
{
  "schema": "plane-tracker/1",
  "view": "list",
  "scope": {"projects": ["PRJ"], "ticket_person": {"relation": "assigned", "actor": "<uuid>"}, "state": "open", "text": "formulario", "order": "rank,-sequence", "limit": 20},
  "total": 3,
  "count": 3,
  "results": [ { "...": "campos del vocabulario" } ],
  "summary": null,
  "coverage": {"source": "cache", "as_of": "2026-11-02T12:00:00Z", "age_s": 60, "stale": false, "complete": null, "unavailable": [],
               "detail": {"text_fields": ["title", "labels"], "history": {"verified": 2, "total": 3}}},
  "notes": [{"code": "history_partial", "text": "Historial de asignación verificado en 2 de 3 tickets.", "hint": "plane-tracker sync --history"}]
}
```

| Clave | Tipo | Regla |
| :--- | :--- | :--- |
| `schema` | cadena | `plane-tracker/<n>`; un cambio incompatible sube `<n>` y exige una decisión. |
| `view` | cadena | una de las vistas registradas: `list`, `get`, `report time`, `report flow`, `worklog check`, `labels`, `projects`, `whoami`, `attachment list`, `outbox list`. |
| `scope` | objeto | el alcance **resuelto**, solo con las dimensiones que la vista acepta. **Opcional**: `get`, `whoami` y `attachment list` no lo llevan (su alcance es un ticket o la identidad, en `results`). |
| `total` | entero | recuento antes del límite. |
| `count` | entero | `len(results)`; nunca mayor que `total` ni que `scope.limit`; sin límite (reportes) `count == total`. |
| `results` | lista | filas con **solo** campos del vocabulario de su familia. |
| `summary` | objeto o null | agregados que no son filas; solo las vistas con familia de resumen. |
| `coverage` | objeto | obligatorio. `complete` es `true`, `false` o `null` (**no verificado**: nunca equivale a completo) y describe la **fuente** (la caché frente al servidor), no si la página muestra todo: para eso están `total`, `count` y la nota `truncated`. `complete: true` es incompatible con una nota `warn`. |
| `notes` | lista | `{code, text, hint?}`; el agente ramifica por `code`. Se derivan de la cobertura, el resultado y el alcance, más las propias de la vista. Orden: avisos (`warn`) antes que informativas (`info`) y luego por código. |

Vocabulario del alcance y la cobertura (una línea por conjunto; F4 las compara con `vocabulary.py`):

- Dimensiones: `projects`, `person`, `period`, `state`, `text`
- Controles: `limit`, `refresh`, `offline`, `verbose`, `brief`
- Claves de `scope`: `projects`, `ticket_person`, `hours_author`, `period`, `state`, `text`, `order`, `limit`, `track`, `worker_type`
- Relaciones de persona: `assigned`, `created`, `involved`
- Estados: `open`, `all`
- Claves de `coverage`: `source`, `as_of`, `age_s`, `stale`, `complete`, `unavailable`, `detail`
- Valores de `coverage.source`: `cache`, `api`, `snapshot`, `local`, `mixed`
- Notas siempre visibles: `truncated`, `text_looks_like_id`
- Claves de `coverage.detail`: `history`, `text_fields`, `hours_scope`, `hours_verified`, `capped`, `legacy`, `forbidden`, `rate_budget_exhausted`, `assignment_snapshot`, `count_mismatch`, `comments`, `metadata_only`, `include`
- Valores de `get --include`: `attachments`, `links`, `relations`, `children`
- Incluibles cubiertos por `get`: `attachments`, `links`

`person` se reparte en `ticket_person` (qué tickets) y `hours_author` (de quién son las horas). Los controles no van en el sobre, salvo `limit`, que se repite en `scope`.

Serialización: `ensure_ascii=False`, claves ordenadas, separadores compactos. Mismo estado, reloj y zona horaria dan bytes idénticos.

Las notas informativas (`info`) solo salen con `--verbose`, salvo las siempre visibles (`truncated`, `text_looks_like_id`: sin ellas un agente concluiría de más); los avisos (`warn`) siempre y llevan `hint` (el remedio, como comando cuando existe). Lo que ya va en `notes` o `coverage` no se repite por stderr en modo `--json`.

## Vocabulario por familia

Un nombre por concepto, en inglés y minúsculas, igual en todas las vistas. Una clave fuera de su familia hace fallar la validación. Tipos: `str`, `int`, `num`, `bool`, `list`, `dict`; `?` admite null y `!` marca el campo obligatorio.

### Familia `ticket`

Vistas `list` y `get`. Las filas breves (`list --brief`) llevan solo `ticket`, `title`, `state`, `state_group`, `project`, que son también los campos obligatorios.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `ticket` | `str!` | etiqueta `PRJ-12` |
| `uuid` | `str` | UUID del ticket; siempre en `get`, ausente en listas |
| `title` | `str!` | título |
| `state` | `str!` | **nombre** del estado (`unknown` si la caché no lo conoce); el UUID no se expone |
| `state_group` | `str!` | `backlog`, `unstarted`, `started`, `completed`, `cancelled`; `triage` puede aparecer y `unknown` si la caché no conoce el estado |
| `priority` | `str` | `urgent`, `high`, `medium`, `low`, `none` |
| `project` | `str!` | identificador del proyecto |
| `assignees` | `list` | `{id, name}` asignados ahora |
| `created_by` | `str?` | UUID del creador |
| `labels` | `list` | nombres de etiqueta |
| `start_date` | `str?` | fecha de inicio |
| `target_date` | `str?` | fecha objetivo |
| `created_at` | `str?` | ISO UTC |
| `completed_at` | `str?` | ISO UTC |
| `plane_updated_at` | `str?` | ISO UTC; cuándo lo tocó Plane |
| `reasons` | `list` | por qué entra en una selección de persona |
| `assignment_events` | `list` | `{at, kind, user_id, user_name}` medidos |

### Familia `ticket_detail`

Vista `get`: todos los campos de `ticket` más los siguientes. `links` y `attachments` solo se leen si se piden (`--include attachments,links` o `--all`; cada uno cuesta 1 GET) y, si se piden, van aunque estén vacíos (vacío = medido). `relations` y `children` se aceptan en `--include` pero **aún no están implementados**: producen el aviso `include_not_covered` y dejan `complete` en `null` (su verificación contra la API real quedó pendiente).

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `description` | `str?` | descripción |
| `comments` | `list` | `{id, author, created_at, text}` |
| `links` | `list` | solo con `get --include links` (o `--all`): `{id, title, url, created_at}` |
| `attachments` | `list` | solo con `get --include attachments` (o `--all`): `{id, name, size, created_at}` |
| `flow` | `dict` | con `get --history`: los campos de la familia `flow` sin `ticket` ni `title` |

### Familia `hours`

Vista `report time`. `author` es el UUID de quien registró las horas (`null` = sin autor registrado). `provenance` indica por campo `measured` o `default`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `ticket` | `str!` | etiqueta del ticket |
| `project` | `str` | identificador del proyecto |
| `date` | `str!` | fecha |
| `start_time` | `str!` | hora de inicio |
| `end_time` | `str!` | hora de fin |
| `minutes` | `int!` | duración |
| `track` | `str` | pista |
| `capacity` | `str` | balde de capacidad |
| `phase` | `str` | fase |
| `role` | `str` | rol |
| `worker_type` | `str` | tipo de trabajador |
| `notes` | `str` | notas |
| `author` | `str?` | UUID del autor |
| `provenance` | `dict` | `measured` o `default` por campo |

### Familia `flow`

Vista `report flow`. Son los nombres vigentes de `flow_metrics.py`, que se conservan.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `ticket` | `str!` | etiqueta del ticket |
| `title` | `str` | título |
| `outcome` | `str!` | `completed`, `cancelled` u `open` |
| `flags` | `list` | marcas de calidad del dato |
| `created` | `str?` | creación |
| `closed` | `str?` | cierre |
| `lead_minutes` | `num?` | lead time |
| `cycle_active_minutes` | `num?` | cycle time activo |
| `cycle_gross_minutes` | `num?` | cycle time bruto |
| `by_state_minutes` | `dict` | minutos por estado |
| `effort_compute_minutes` | `num?` | esfuerzo calculado |
| `effort_clock_minutes` | `num?` | esfuerzo registrado |
| `worklogs` | `int` | registros de horas |
| `worklogs_before_created` | `int` | registros anteriores a la creación |
| `worklogs_after_closed` | `int` | registros posteriores al cierre |
| `effort_clock_over_cycle` | `num?` | esfuerzo registrado sobre el cycle time |
| `transitions` | `list` | solo en `get --history`: `{at, from, to}` con nombres de estado |

### Familia `check`

Vista `worklog check`. Los códigos de `code` son un espacio propio (ver más abajo).

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `code` | `str!` | código de comprobación |
| `ticket` | `str!` | etiqueta del ticket |
| `comment_id` | `str?` | comentario afectado |
| `detail` | `str` | explicación |

### Familia `label`

Vista `labels`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `id` | `str!` | UUID |
| `name` | `str!` | nombre |
| `color` | `str` | color |

### Familia `project`

Vista `projects`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `id` | `str!` | UUID |
| `identifier` | `str!` | identificador (`PRJ`) |
| `name` | `str!` | nombre |

### Familia `whoami`

Vista `whoami`: una sola fila con la configuración activa. `source` indica de dónde sale la identidad: `actor_env` (`PLANE_ACTOR_UUID`), `username` (resuelta por `PLANE_USERNAME`) o `unset`. `status` es `ok`, `unresolved` (el usuario no coincide con ningún miembro; salida 1) o `unset`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `workspace` | `str!` | workspace activo |
| `base_url` | `str` | URL de Plane |
| `actor` | `str?` | UUID resuelto |
| `username` | `str?` | `PLANE_USERNAME`, si está definido |
| `source` | `str!` | origen de la identidad |
| `status` | `str!` | resultado de la comprobación |

### Familia `attachment`

Vista `attachment list`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `ticket` | `str!` | ticket al que pertenece |
| `id` | `str!` | UUID del adjunto |
| `name` | `str?` | nombre del archivo |
| `size` | `int?` | tamaño en bytes |
| `created_at` | `str?` | ISO UTC |

### Familia `outbox_item`

Vista `outbox list`: registros de la cola de salida de `comment add`. `scope.state` es `open` o `all` (`--all`).

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `id` | `int!` | número del registro |
| `client_id` | `str!` | clave de idempotencia |
| `state` | `str!` | `pending`, `sending`, `sent`, `failed` o `dropped` |
| `ticket` | `str!` | etiqueta del ticket |
| `track` | `str` | pista |
| `date` | `str` | fecha del registro de horas |
| `start_time` | `str` | hora de inicio |
| `minutes` | `int?` | duración |
| `attempts` | `int` | intentos de envío |
| `maybe_delivered` | `bool` | pudo haberse enviado |
| `last_error` | `str?` | último error |
| `plane_comment_id` | `str?` | comentario publicado |
| `created_at` | `str` | creación |
| `preview` | `str` | vista previa de 80 caracteres |

### Resumen `hours_summary`

`summary` de `report time`. `by_day`, `by_project` y `by_capacity` son listas de `{key, minutes}`; lo no medido por defecto va en `by_capacity` bajo la clave `undeclared`, nunca sumado a `deep_work`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `by_day` | `list` | minutos por día |
| `by_project` | `list` | minutos por proyecto |
| `by_capacity` | `list` | minutos por balde |
| `effort_clock_minutes` | `int` | esfuerzo registrado |
| `effort_compute_minutes` | `int` | esfuerzo calculado |

### Resumen `flow_summary`

`summary` de `report flow`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `tickets` | `int` | tickets considerados |
| `completed` | `int` | completados |
| `cancelled` | `int` | cancelados |
| `open` | `int` | abiertos |
| `excluded` | `int` | excluidos |
| `n_lead` | `int` | muestras de lead time |
| `n_cycle` | `int` | muestras de cycle time |
| `median_lead_minutes` | `num?` | mediana de lead time |
| `median_cycle_minutes` | `num?` | mediana de cycle time |

### Resumen `check_summary`

`summary` de `worklog check`.

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `ok` | `bool` | sin errores de comprobación |
| `unreachable` | `int` | tickets que no se pudieron comprobar |

### Objetos anidados

Claves permitidas de cada elemento de estas listas dentro de una fila.

| Campo | Claves |
| :--- | :--- |
| `assignees` | `id`, `name` |
| `assignment_events` | `at`, `kind`, `user_id`, `user_name` |
| `comments` | `id`, `author`, `created_at`, `text` |
| `transitions` | `at`, `from`, `to` |
| `attachments` | `id`, `name`, `size`, `created_at` |
| `links` | `id`, `title`, `url`, `created_at` |

## Códigos de comprobación (`worklog check`)

Espacio propio (`check_code`), distinto de los códigos de nota y de error.

| Código | Significado |
| :--- | :--- |
| `duplicate` | varias filas locales para el mismo comentario |
| `orphan` | el comentario ya no existe en Plane |
| `mismatch` | la fila local difiere de la telemetría del comentario |
| `missing_local` | comentario con telemetría sin fila local |
| `pending` | fila local en cola de publicación |
| `unlinked` | fila local sin comentario asociado |
| `no_block` | el comentario no lleva telemetría |
| `unreachable` | no se pudo consultar el ticket en Plane |

## Registro de códigos de nota

Severidad (`info`, `warn`) y origen. Agregar uno exige añadirlo aquí y en `vocabulary.py`. Los de origen `cobertura`, `resultado` y `alcance` se **derivan** automáticamente; los de origen `vista` los aporta la consulta; `internal` solo lo escribe el sobre.

| Código | Sev. | Origen | Cuándo | Remedio (`hint`) |
| :--- | :---: | :--- | :--- | :--- |
| `truncated` | info | resultado | `count < total` (siempre visible) | — |
| `cache_stale` | warn | cobertura | se sirvió vencido porque Plane no respondió | reintentar con red o `--refresh` |
| `source_unavailable` | warn | cobertura | proyectos sin datos ni caché | conectar y `--refresh` |
| `source_forbidden` | warn | cobertura | proyectos sin acceso (403) | revisar la membresía; se omiten |
| `rate_budget_exhausted` | warn | cobertura | se detuvo antes de agotar el límite de tasa; resultado parcial | reintentar más tarde |
| `legacy_cache` | warn | cobertura | tickets sin datos de asignación (caché anterior) | conectar para renovarla |
| `assignment_snapshot` | info | cobertura | la asignación es la de la última sincronización | `--refresh` |
| `history_partial` | warn | cobertura | historial de asignación verificado en `a` de `b` | `sync --history` |
| `hours_local_only` | warn | cobertura | las horas salen solo de la base local de esta máquina | `report time --refresh` |
| `hours_unsigned` | warn | vista | registros de horas sin autor registrado | `report time --refresh` |
| `hours_defaulted` | warn | vista | horas con campos por defecto no medidos | corregir el comentario o sincronizar de nuevo |
| `single_project` | info | alcance | alcance de un solo proyecto | `--all-projects` |
| `cache_capped` | warn | cobertura | el proyecto supera el máximo sincronizable | acotar el alcance |
| `pending_unpublished` | warn | vista | comentarios en cola sin publicar que afectan el resultado | `outbox flush` |
| `text_looks_like_id` | info | vista | el texto parece un ticket (`PRJ-12`); siempre visible | `get PRJ-12` |
| `include_not_covered` | warn | vista | se pidió `relations` o `children` (o `--all`), que `get` aún no implementa | solo se incluyen `attachments` y `links` |
| `internal` | warn | envelope | deriva del sobre detectada en producción | informar el defecto |

## Sobre de error

En `--json` los errores salen por **stdout** como objeto y con el código de salida correspondiente; en texto, mensaje y pista por stderr. Claves: `schema`, `status` (`error`), `code`, `message`, `hint?`, `exit`, `detail?` (por ejemplo `{"status": 404}` en `http_error`).

```json
{"schema": "plane-tracker/1", "status": "error", "code": "unknown_project",
 "message": "Proyecto 'XYZ' no encontrado.", "hint": "Opciones: PRJ, OPS. Usa -p PRJ.", "exit": 1}
```

| Código | Salida | Cuándo |
| :--- | :---: | :--- |
| `usage` | 2 | argparse, nombre retirado, verbo ausente o flag no soportado por la vista |
| `unknown_project`, `unknown_state` | 1 | valor inexistente en el workspace |
| `unknown_label` | 1 | etiqueta inexistente en el workspace |
| `actor_unknown` | 1 | filtro de persona sin `PLANE_ACTOR_UUID` ni `PLANE_USERNAME` |
| `bad_period`, `bad_date` | 1 | fecha mal formada o rango invertido |
| `not_found` | 1 | ticket o recurso inexistente |
| `duplicate` | 1 | `create` con título repetido reciente |
| `queue_full` | 1 | límite de la cola de salida |
| `env_missing` | 1 | falta una variable de entorno obligatoria |
| `refused` | 1 | operación destructiva rechazada por seguridad |
| `http_error` | 1 | error HTTP definitivo |
| `plane_unavailable` | 3 | Plane no responde y no hay alternativa local |
| `no_cache` | 3 | sin Plane y sin caché local |

Tabla fija de salida: **0** éxito (o comentario encolado); **1** error definitivo o de validación; **2** uso; **3** Plane no disponible.

## Sobre de escritura

```json
{"schema": "plane-tracker/1", "status": "ok", "action": "update", "ticket": "PRJ-12", "uuid": "<uuid>"}
```

Los mismos nombres que las lecturas; `status` es `ok`, `queued` (comentario encolado) o `error`. Se implementa en la fase 8 del plan.

## Evolución

- Tras declarar `plane-tracker/1` estable, solo se **añaden** campos y códigos; renombrar o quitar sube la versión.
- Todo cambio del vocabulario pasa por una decisión, actualiza este documento y `vocabulary.py` y regenera los golden con revisión manual.
