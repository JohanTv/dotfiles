---
id: "0019"
title: Filtros de persona en list y historial de asignación medido
status: aceptado
created: 2026-11-02
summary: "`list --mine|--created|--involved` sobre la caché; `--involved` une asignado, creador, horas tuyas y asignado alguna vez, con razón y cobertura declaradas."
---

# 0019 · Filtros de persona en `list` y historial de asignación medido

Relacionado: [principles.md](../principles.md) (P3, P4, P5, local-first), RFC [0005](../rfcs/0005-vista-personal-agenda-y-backlog/README.md) (fase 0), defecto [0017](../defects/0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md); el defecto [0020](../defects/0020-etiquetas-de-la-cache-de-tickets-siempre-vacias.md) (etiquetas vacías) se corrigió aparte.

## Contexto

La herramienta no podía responder "¿qué tengo yo?": la caché de tickets no guardaba asignados ni creador, `list` no filtraba y `search` solo busca texto. Los tickets además cambian de manos (se empiezan, se asignan, se reasignan y vuelven), así que "asignado ahora" no basta para contestar "¿dónde estuve metido?".

## Decisión

- **`--mine` es "asignado ahora"**, `--created` es el creador y **`--involved` es una unión con razón por ticket**: asignado, creador, horas tuyas (base local, por autor) y asignado alguna vez (historial medido). "Involucrado" no se guarda: se calcula en cada consulta.
- **La carga y la agenda usan `--mine`**, no `--involved` (P4): un ticket reasignado a otro ya no es carga mía.
- **Los filtros viven en `list`, no en `search`** (que es anti-duplicados: 5 resultados, un proyecto). Sin filtros, `list` sigue pidiendo a la API y su `--json` crudo no cambia; con filtro, lee la caché (local-first) y avisa su antigüedad.
- **Identidad cacheada y fallo cerrado.** `PLANE_USERNAME` se resuelve una vez y se recuerda; sin identidad el filtro termina con error de uso y nunca devuelve todo.
- **Historial en una tabla durable** (`assignment_events`), alimentada con las mismas actividades que ya se leen para las transiciones de estado, para que sobreviva al borrado y reinserción de `issues_cache`. Se trae bajo demanda (`--refresh-history`, con presupuesto, parada ante 429 o circuito abierto y reanudable), no en cada sincronización.
- **Una caché anterior** (sin datos de asignación) se renueva sola si hay conexión; sin conexión, esos tickets se cuentan como "sin datos", no como "no asignados".

## Lo que la herramienta no afirma (P5)

- Que no estuviste involucrado porque falte un evento: el aviso dice "verificado en X de Y tickets".
- Quién tiene el ticket ahora si la caché está vencida: la asignación es la de la última sincronización y se muestra su edad.
- Duraciones de asignación ni quién lo tuvo entre dos eventos: solo los cambios medidos, en orden.
- Que quien registró horas fuera el asignado, ni que no hay horas: salen solo de la base local de esta máquina (defecto 0017).

## Autoría de las horas

- `worklogs.author_id` guarda el UUID de quien registró las horas. `comment add` y `comment edit` lo toman de la identidad conocida **sin red** (`PLANE_ACTOR_UUID` o el UUID ya resuelto de `PLANE_USERNAME`), así que no añaden peticiones; `sync` lo toma del autor del comentario en Plane.
- **NULL significa "sin autor registrado"** (filas anteriores o escritas sin identidad) y nunca se supone propio: `--involved` lo muestra como "horas sin autor registrado" y avisa cuántas hay. `report --refresh` las completa cuando el comentario está en Plane. Un autor conocido nunca se borra con un valor desconocido.
- `delete` trata las horas locales sin autor como propias (se crearon en esta máquina) y las de otro autor conocido como ajenas, que bloquean el borrado.

## Por verificar contra una instancia real

- Verificado en una instancia real (2026-11-02): `assignees` llega como lista de UUID (cadenas) y `created_by` como UUID. Sigue por verificar que `created_by` sea siempre el creador (una automatización con clave de servicio lo cambia).
- La forma del evento de asignación en las actividades (`field == "assignees"`, UUID en `new_identifier` al añadir y en `old_identifier` al quitar). El parser es tolerante, pero el golden usa esa forma supuesta.
- Que reasignar cambie el `updated_at` del ticket (la incrementalidad del barrido lo asume) y que la asignación al crear el ticket genere actividad.

## Consecuencias

- `--all-projects` y `--refresh-history` cuestan peticiones; por eso son opcionales. El comentario ("comentó") no cuenta como involucración: costaría una petición por ticket y es ruido.
- La caché sigue limitada a 2000 tickets por proyecto; ahora lo avisa en vez de truncar en silencio.
- `delete` limpia también el historial de asignación del ticket.
