---
id: "0005"
title: Vista personal de actividades (agenda) y registro de diferimiento del backlog
status: borrador
created: 2026-10-31
summary: "`list --mine`, panel `agenda` con carga, vencidos y backlog propio, y registro del motivo por el que se difiere algo importante."
---

# 0005 · Vista personal de actividades (agenda) y registro de diferimiento del backlog

- **Área:** `list`, comando nuevo `agenda`, `comment add` (bloque de diferimiento), caché local.
- **Principios:** ver [`principles.md`](../../principles.md).

## Documentos de esta carpeta

- [`cobertura-actual-de-principios.md`](./cobertura-actual-de-principios.md): qué cubre hoy la herramienta de cada principio y qué falta (el análisis que origina este RFC).
- [`reporte-ideal.md`](./reporte-ideal.md): maqueta de `agenda` y de dónde sale cada dato.

## Contexto

La herramienta registra y reporta tiempo, pero no responde a "¿cuál es mi trabajo abierto, qué está vencido y qué dejé de lado, y por qué?". Es una carencia de capacidad, no un defecto.

## Evidencia verificada

| Hecho | Consecuencia |
| :--- | :--- |
| `issues_cache` no guarda asignados ni creador; `create` y `update` no los aceptan; `list` no los muestra | El caché local no puede responder "mis tareas", ni sin conexión. |
| `list` entrega los últimos N tickets de un proyecto, sin filtro por estado, persona ni proyectos cruzados | Hay que cruzar a mano la API, la caché y los worklogs. |
| El JSON crudo de la API sí trae `assignees` y `created_by` | El dato existe; falta usarlo. |
| `report` solo lee `worklogs` y agrupa por proyecto | El backlog no aparece en ningún informe; el reporte no compara contra los baldes de capacidad. |
| `target_date` existe y no se evalúa en ningún comando | Los vencidos pasan sin señal. |

## Propuesta

### Fase 0 · datos y filtros
- Guardar `assignees` y `created_by` en `issues_cache`; mostrar el asignado en `list`.
- `list --mine`, `--open`, `--created`, `--involved`, `--all-projects`. "Involucrado" = asignado, creador, con horas tuyas o asignado alguna vez.
- **Implementada** (la definición de "involucrado" y sus límites están en la decisión [0019](../../decisions/0019-filtros-de-persona-y-historial-de-asignacion.md)); el resto de las fases sigue sin implementar.

### Fase 1 · `agenda`
Se construye como la vista `report agenda` del modelo de [0021](../0021-arquitectura-de-lectura-consultas-y-vistas/README.md) (fase 4 de su plan), sobre la misma selección de tickets que `list`; no se implementa como un comando aparte.

Vista personal de lectura rápida, sin enviar nada. Secciones:

1. **Carga:** tickets en curso (frente a un límite sugerido), en revisión, vencidos y sin movimiento hace más de N días.
2. **En curso (compromisos):** prioridad, vencimiento, antigüedad y último movimiento.
3. **Siguiente:** pendientes y en revisión.
4. **Backlog propio con motivo de diferimiento.**
5. **Trabajo invisible de la semana:** horas de soporte y coordinación frente a la meta de cada balde.
6. **Expectativas:** lo comprometido al inicio de la semana frente a lo cerrado, y la mediana de cycle time por tipo de ticket.

### Fase 2 · registro de diferimiento
Un comentario estructurado con bloque oculto (el mismo mecanismo que el worklog) que registra: motivo del diferimiento, costo de no hacerlo, quién decidió y fecha de revisión. Evita añadir etiquetas a una taxonomía ya estricta y mantiene a Plane como fuente única de los tickets.

### Fase 3 · honestidad del reporte
- Resolver el "standby externo" ([0003](../../defects/0003-standby-externo-sin-fuente-de-datos.md), [0006](../0006-standby-externo-fuente-de-datos.md)).
- Avisar cuando el caché de worklogs esté desfasado.
- Agrupar por balde y no solo por proyecto.

### Fase 4 · privacidad por niveles
Un modo personal completo y un modo de envío explícito y filtrado: la visibilidad hacia arriba es una decisión de la persona que trabaja, no un efecto por defecto.

## Tensiones a resolver

- **Visibilidad hacia arriba frente a autonomía:** separar la vista personal de lo que se decide compartir.
- **Trabajo invisible frente a carga de registro:** registrar el toil debe costar un comando.
- **Datos honestos frente a expectativas:** mostrar tendencias y no puntajes (ley de Goodhart).
- **Backlog frente a compromiso:** backlog es intención sin fecha; las fechas de compromiso van solo en lo que está en curso.

## Criterios de aceptación (por fase)

- Fase 0: `list --mine --open` responde sin conexión desde la caché y coincide con la API.
- Fase 1: `agenda` muestra carga, vencidos y estancados con datos reales y sin llamadas de escritura.
- Fase 2: un diferimiento registrado reaparece en `agenda` con su fecha de revisión.
- Fase 3: ningún reporte afirma un dato que no tiene fuente.
- Fase 4: el modo de envío no incluye nada que la persona no haya confirmado.
