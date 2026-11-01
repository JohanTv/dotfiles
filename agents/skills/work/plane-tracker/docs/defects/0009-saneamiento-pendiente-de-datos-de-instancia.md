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

## Procedimiento previsto para el historial (no ejecutado)

Autorizado por la persona responsable del repositorio el 2026-10-31; **todavía no se ha ejecutado**: el historial publicado sigue conteniendo los datos. Las reglas de reemplazo se mantienen **fuera del repositorio** (listarlas aquí volvería a publicar los datos).

1. Copia de seguridad completa (`git clone --mirror`) en una ubicación local; contiene los datos sensibles y se borra al verificar.
2. Reescritura en un **clon aparte**, no en el árbol de trabajo vivo, con una herramienta que conozca la ruta de cada archivo: solo se tocan documentos (`.md`) y el ejemplo de configuración. No se tocan el código (los valores por defecto del CLI) ni rutas funcionales de otros scripts.
3. Verificación antes de publicar: el historial reescrito no contiene los términos, los árboles fuera de los archivos previstos son idénticos a los originales y la suite de pruebas pasa.
4. Publicación solo de la rama principal con `--force`; la rama de trabajo se publica después con normalidad.
5. Mover el repositorio local a la historia nueva con `git reset --keep`, que conserva cambios locales no relacionados y aborta si hay conflicto.
6. Cada clon adicional (otras máquinas) debe ejecutar `git fetch origin` y `git reset --hard origin/main` **antes** de hacer `push`, o volvería a publicar la historia antigua.

Límites que hay que asumir: la reescritura no borra copias ya hechas (clones, forks), y GitHub puede seguir sirviendo los commits antiguos por su identificador hasta que su soporte los purgue.

## Criterio de cierre

- Cada fila resuelta, o descartada con la razón registrada aquí.
- Para el historial: decisión explícita de reescribirlo o de asumirlo, anotada en este documento.
