---
id: "0009"
title: Saneamiento pendiente de datos de instancia y de personas en el repositorio
status: abierto
created: 2026-10-31
summary: Quedan ejemplos con claves de proyecto reales, un workspace por defecto en el código y datos ya publicados en el historial.
---

# 0009 · Saneamiento pendiente de datos de instancia y de personas en el repositorio

- **Decisión que lo origina:** [0007](../decisions/0007-documentos-agnosticos-de-instancia.md).

## Contexto

Los documentos actuales se sanearon en el mismo cambio que creó `docs/` (IP, workspace, nombres de personas y de clientes, horas reales de reuniones). Este defecto registra lo que ese cambio no cubre.

## Pendiente

| Elemento | Ubicación | Nota |
| :--- | :--- | :--- |
| Workspace real como valor por defecto en el código | `scripts/plane_cli/cli.py` (`PLANE_WORKSPACE_SLUG`), `scripts/plane_cli/db.py` (columna `workspace`) | Cambiar el comportamiento afecta tests y goldens; decidir si el slug pasa a ser obligatorio. |
| Claves de proyecto reales como ejemplos (`OMNIFY-175`, `OPS-44`...) | `SKILL.md`, `references/*`, `docs/*` | Decidir si se neutralizan a `PROJ-123` o se aceptan como ejemplos. |
| Reglas del perfil de trabajo con ejemplos de personas | `agents/rules/src/work.md` | Fuera de la carpeta de la skill; mismo repositorio público. |
| Datos ya publicados en el historial de git | Commits anteriores a este cambio | Quitarlos de los archivos no los borra; reescribir el historial exige autorización explícita (afecta lo ya publicado). |

## Criterio de cierre

- Cada fila resuelta, o descartada con la razón registrada aquí.
- Para el historial: decisión explícita de reescribirlo o de asumirlo, anotada en este documento.
