---
id: "0024"
title: Las lecturas piden más datos de los que usan
status: corregido
created: 2026-11-02
closed: 2026-11-02
summary: "`list` baja hasta 1000 tickets con su descripción para imprimir 15, `resolve_issue` recorre el listado paginado del proyecto para encontrar un ticket y `limit` no limita nada porque la API lo ignora."
---

# 0024 · Las lecturas piden más datos de los que usan

- **Área:** `cmd_read.py` (`list`), `resolve.resolve_issue`, `cache._fetch_all_issues`, `api` (cabeceras de tasa).
- **Relacionado:** RFC [0021](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/README.md) y [`hechos-de-la-api.md`](../rfcs/0021-arquitectura-de-lectura-consultas-y-vistas/hechos-de-la-api.md).

## Síntomas (verificados)

- **`limit` no limita:** la API ignora `limit`; el parámetro real es `per_page` (por defecto 1000). `list` pide `?limit=50` y recibe todo el proyecto (unos 487 KB y 3 a 6 s para 217 tickets, porque cada ticket trae su `description_html`) para imprimir 15.
- **`resolve_issue` recorre el listado** paginado del proyecto buscando el `sequence_id`, cuando existe `GET workspaces/{ws}/issues/{PRJ}-{n}/` (1 GET). Lo usan `get`, `report flow`, `worklog check`, `update` y otros.
- **La caché descarga la descripción** de todos los tickets aunque nunca la usa (`fields=` la omite).
- **Las cabeceras de tasa se descartan** (`X-RateLimit-Remaining`/`Reset`): con unas 60 peticiones por ventana, una lectura en frío cuesta `3N + 1` GET y puede agotar la cuota sin que nadie lo sepa.

## Solución propuesta

1. `per_page=100` explícito y `fields=` sin descripción en la sincronización de tickets.
2. Resolver el ticket por su identificador (1 GET) y usar el listado solo como respaldo.
3. Exponer las cabeceras de tasa en `api.py` y detenerse con cobertura parcial antes de agotar la cuota.
4. Dejar de pasar `limit` (no tiene efecto).

## Corrección aplicada

1. `cache._fetch_all_issues` y `worklog_sync._candidates` usan `per_page=100` y `fields={ISSUE_FIELDS}` excluyendo descripciones HTML.
2. `resolve_issue` ahora recibe `issue_ref` opcional y resuelve en 1 GET (`GET workspaces/{ws}/issues/{PRJ}-{n}/`) antes de caer en el listado paginado como fallback.
3. Todos los comandos que interactúan con tickets (`cmd_update`, `cmd_comment_add`, `cmd_link`, `cmd_attachment_*`, `cmd_delete`, `outbox_flush`, `fetch_attachments`, `audit_worklogs`) propagan `issue_ref` obtenido de `resolve_project_and_seq`.
4. `api.py` expone `rate_limit()` capturando `X-RateLimit-Remaining` y `X-RateLimit-Reset` en cada petición, y `cache` junto a `worklog_sync` respetan la reserva de tasa deteniéndose con cobertura parcial.
5. Los golden tests reflejan la reducción directa de llamadas a `issues/` a favor de llamadas únicas a `issues/{PRJ}-{n}/`.

## Criterio de cierre

- `get` y las operaciones sobre un ticket cuestan 1 GET para resolverlo; la sincronización de un proyecto descarga mucho menos que antes. Cobertura de pruebas completa en verde (445 pruebas).
