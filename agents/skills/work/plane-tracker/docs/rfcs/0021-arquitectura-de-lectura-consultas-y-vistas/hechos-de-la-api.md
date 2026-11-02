# Hechos verificados de la API de Plane

Parte de [0021](./README.md). Observados el 2026-11-02 contra una instancia real con **solo peticiones GET** (unas 115, sin 429 ni 5xx). Este documento recoge **formas**, nunca datos de la instancia (decisión [0007](../../decisions/0007-documentos-agnosticos-de-instancia.md)). Donde no se pudo comprobar, se marca **[S]**. Corrige varias suposiciones de la versión 1 del RFC y de los defectos 0010 y 0017.

## Paginación y filtros del listado de tickets

| Hecho | Detalle |
| :--- | :--- |
| Sobre paginado | `grouped_by`, `sub_grouped_by`, `total_count`, `next_cursor`, `prev_cursor`, `next_page_results`, `prev_page_results`, `count`, `total_pages`, `total_results`, `extra_stats`, `results`. Lo mismo en comentarios, actividades, estados, etiquetas y proyectos. |
| Cursor | Forma `per_page:página:desplazamiento` (por ejemplo `50:1:0`). |
| **`per_page`** | Funciona. El tamaño por defecto observado es **1000** (la documentación pública dice 20 y máximo 100). El máximo real **no se probó** [S]. |
| **`limit`** | **Se ignora en silencio**: `limit=1` devolvió todos los tickets. Cualquier `limit=N` del código actual (`limit=15`, `limit=50`, `limit=100`) no limita nada. |
| **Filtros de servidor** | **Se ignoran en silencio** (respuesta 200 con todas las filas): `assignees`, `assignee`, `created_by`, `state_group`, `updated_at__gte`, `updated_at__gt`, `updated_after`. La documentación pública tampoco los lista. Funcionan solo `order_by` (`updated_at` en ambos sentidos), `per_page`, `cursor`, `fields` y `expand`. |
| `fields=` | Funciona y reduce mucho el tamaño (de unos 487 KB a unos 70 KB en un proyecto de 217 tickets al omitir la descripción). Nombres de contadores (`sub_issues_count`, `attachment_count`, `link_count`, `comment_count`) **no existen**: devuelven solo `id`. |
| Coste de una página | Cada ticket lleva `description_html`: unos 2 KB por ticket; 217 tickets = 487 KB en 3 a 6 s en una sola respuesta. |
| `total_count` | Llega en cada página. Es el dato que permite saber si se listó **todo** el proyecto. |

**Consecuencia:** `list --mine`, `--created` y los filtros de fecha son **siempre locales**; una sincronización incremental por filtro de fecha no es posible (solo `order_by=-updated_at` con corte local y `fields=`).

## Forma de los campos

- `assignees`: lista de **cadenas UUID** (no objetos); `labels`: lista de UUID; `state`: UUID; `created_by`: cadena UUID; `updated_by`: cadena o null; `archived_at`: null o fecha; `sequence_id`: entero.
- Marcas de tiempo: `AAAA-MM-DDThh:mm:ss.ffffffZ`.
- `parent` y `is_draft` existen. Un proyecto puede traer `is_member: false` y `archived_at` no nulo.
- `GET /members/` devuelve una **lista plana** (sin sobre ni paginación) con `id`, `first_name`, `last_name`, `email`, `display_name`, `role` (entero), avatar.
- Estados: grupos observados `backlog`, `unstarted`, `started`, `completed`, `cancelled`; el campo `is_triage` existe, así que el grupo `triage` puede aparecer **[S]**.

## Proyectos sin acceso

Un proyecto con `is_member: false` responde **403** en `issues/`, `states/` y `labels/`. Un proyecto archivado también aparece en el listado. Con el código actual, un 403 en una lectura termina el programa con código 1 (`fail_http`), así que **`list --all-projects` falla hoy** en un workspace así (en la prueba: 15 GET en 13,9 s y salida vacía).

## Comentarios y actividades

- **Comentarios:** mismo sobre; por defecto 1000 por página; `per_page=1` pagina bien. Claves: `access`, `actor`, `attachments`, `comment_html`, `created_at`, `created_by`, `deleted_at`, `description`, `edited_at`, `external_id`, `external_source`, `id`, `is_member`, `issue`, `parent`, `project`, `updated_at`, `updated_by`, `workspace`. `actor` coincidió con `created_by` en todas las muestras.
- **Actividades:** orden ascendente por `created_at`. Evento de asignados: `field: "assignees"`, `verb: "updated"`, `comment: "added assignee "` o `"removed assignee"`.
  - **Alta:** `old_value: ""` (cadena vacía, no null), `old_identifier: null`, `new_value` = nombre visible, `new_identifier` = UUID.
  - **Baja:** `old_value` = nombre visible, `old_identifier` = UUID, `new_value: ""`, `new_identifier: null`.
  - Esto **confirma** la forma que `assignments.py` espera.
  - Estado: `field: "state"` con nombre e identificador en ambos extremos (coincide con `flow.py`). Otros campos: `description` (con el HTML completo viejo y nuevo), `name`, `labels`, `priority`, fechas, relaciones, módulos y ciclos.
- **Crear un comentario no genera actividad.**
- **`updated_at` del ticket:** coincide con su última actividad en 13 de 17 tickets observados y con su último comentario en los demás; los eventos de relación (`blocked_by`) pueden quedar posteriores. Que **reasignar solo** lo actualice es consistente con lo visto pero **no está probado** (todo ticket reasignado cambió después de estado) **[S]**.

## Otros endpoints útiles

| Endpoint | Uso |
| :--- | :--- |
| `GET workspaces/{ws}/issues/{PRJ}-{seq}/` (y la variante `work-items`) | un ticket por su identificador en **1 GET**. Hoy `resolve_issue` recorre el listado paginado del proyecto. |
| `GET workspaces/{ws}/issues/search/?search=texto` (y `work-items/search/`) | búsqueda de texto en **todo el workspace** en 1 GET, **máximo 10** resultados con solo `id`, `name`, `project__identifier`, `project_id`, `sequence_id`, `workspace__slug`; sin estado, grupo ni prioridad; AND entre palabras. **No sustituye** a `list --text` (no ve el estado), pero es un primer filtro barato para una guarda de duplicados. |

## Límite de tasa

Las respuestas 200 traen `X-RateLimit-Remaining` y `X-RateLimit-Reset` (época); **no** traen `X-RateLimit-Limit` ni `Retry-After`. El contador observado bajó de 58 en 58, 57, 56, ... (ventana de **60**; que sea de un minuto no se verificó **[S]**). `api.py` descarta hoy todas las cabeceras.

**Consecuencia:** con 60 peticiones por ventana, una lectura en frío cuesta `3N + 1` GET para `N` proyectos accesibles (proyectos, y por cada uno estados, etiquetas y tickets); con `N ≥ 20` se agota la cuota. `report flow` con más de 15 tickets también.

## Un ticket, enlaces, adjuntos, relaciones y sub work-items

Verificado el 2026-11-02 con GET sobre un ticket real (formas; ningún dato de la instancia).

| Hecho | Detalle |
| :--- | :--- |
| Ticket por etiqueta | `GET workspaces/{ws}/issues/{PRJ}-{n}/` (y `work-items/` con la misma respuesta): 1 GET. |
| Contadores | El ticket **no** trae contadores de enlaces, adjuntos, relaciones ni hijos. Solo `parent` (id o null). Saber si hay algo exige pedirlo. |
| Enlaces | `…/issues/{id}/links/`: sobre paginado (`results`, `total_count`, `next_cursor`, `next_page_results`). Cada elemento: `id`, `title`, `url`, `metadata`, fechas y autor. |
| Adjuntos | `…/issues/{id}/issue-attachments/`: **lista plana**, sin paginación. Cada elemento: `id`, `size`, `created_at`, `attributes {name, size, type}` y otros. |
| Relaciones | Solo con la ruta `…/work-items/{id}/relations/`: un objeto con `blocked_by`, `blocking`, `duplicate`, `finish_after`, `finish_before` y `relates_to`. Con `issues/` responde 404. **La forma de un elemento no se verificó** (no había ninguno). |
| Sub work-items | No existe un endpoint dedicado (`sub-issues/` y `sub-work-items/` dan 404 con ambas rutas). El filtro `?parent=` lo ignora el servidor. El listado acepta `fields=parent`: los hijos solo se pueden resolver con `parent` en la caché local. **No verificado con un ticket que tenga hijos.** |

## Borrado

La documentación pública indica que `DELETE .../work-items/{id}/` responde **204** sin cuerpo. No se probó (la validación era de solo lectura) **[S]**.

## Lo que sigue sin verificar

Que editar un comentario ya existente cambie el `updated_at` del ticket (la sincronización de horas es incremental por ese campo); forma de un elemento de `relations/` y de un hijo real (pendiente: hace falta un ticket con relaciones y otro con sub work-items); máximo real de `per_page`; paginación de más de una página en comentarios y actividades (solo `per_page=1`); un ticket con muchos comentarios (el máximo visto fue 4); comentarios con telemetría de otras personas o parcial en toda la instancia (la muestra fue de unos 41 tickets de unos 234: **0** casos); el 429 y `Retry-After`; `expand=assignees`; que reasignar actualice `updated_at`; que exista el grupo `triage`.
