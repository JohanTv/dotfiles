---
id: "0009"
title: Saneamiento pendiente de datos de instancia y de personas en el repositorio
status: abierto
created: 2026-10-31
summary: El historial publicado ya se reescribió; quedan valores por defecto en el código, claves de proyecto como ejemplos y la purga de copias fuera del repositorio.
---

# 0009 · Saneamiento pendiente de datos de instancia y de personas en el repositorio

- **Decisión que lo origina:** [0007](../decisions/0007-documentos-agnosticos-de-instancia.md).

## Contexto

Los documentos actuales se sanearon en el mismo cambio que creó `docs/` (IP, workspace, nombres de personas y de clientes, horas reales de reuniones), y el historial publicado se reescribió después (ver más abajo). Este defecto registra lo que queda.

## Pendiente

| Elemento | Ubicación | Nota |
| :--- | :--- | :--- |
| Workspace real como valor por defecto en el código | `scripts/plane_cli/cli.py` (`PLANE_WORKSPACE_SLUG`), `scripts/plane_cli/db.py` (columna `workspace`) | Cambiar el comportamiento afecta tests y goldens; decidir si el slug pasa a ser obligatorio. También sigue en el historial, por la misma razón. |
| Identificador de proyecto real como valor por defecto en el código | `scripts/plane_cli/cli.py` (`PLANE_PROJECT_ID`) | Igual que la fila anterior. |
| Claves de proyecto reales como ejemplos (`OMNIFY-175`, `OPS-44`...) | `SKILL.md`, `references/*`, `docs/*` | Decidir si se neutralizan a `PROJ-123` o se aceptan como ejemplos. |
| Copias que no controla el repositorio | Clones, forks y la caché de GitHub | La reescritura no las alcanza (ver "Límites"). |
| Copia de seguridad local previa a la reescritura | Un espejo completo fuera del árbol de trabajo | Contiene los datos antiguos; se borra cuando se dé por verificada la reescritura. |
| Otras máquinas con una copia del repositorio | Cada clon adicional | Deben alinearse con el historial nuevo antes de hacer `push` (ver "Procedimiento"). |

## Reescritura del historial: ejecutada el 2026-10-31

Se sustituyeron, solo en documentos (`.md`) y en el ejemplo de configuración, la IP y el host de la instancia, el slug del workspace, los identificadores de proyecto, los nombres de personas y de clientes. Las reglas de reemplazo se mantienen **fuera del repositorio** (listarlas aquí volvería a publicar los datos).

- **Cómo:** en un clon aparte, con `git filter-branch`, tras una copia de seguridad completa (`git clone --mirror`). No se tocaron el código Python (por los valores por defecto del CLI), el README ni rutas funcionales de otros scripts.
- **Metadatos intactos:** fechas de autor y de commit, autor y mensaje son idénticos commit a commit; solo cambian los identificadores. El gráfico de contribuciones depende de la fecha y del correo del autor, que no cambiaron.
- **Verificación antes de publicar:** 0 apariciones de los términos en todo el historial reescrito fuera de los `.py`; en la punta solo cambió una línea de `agents/rules/src/work.md`; la suite de pruebas pasó sobre el historial nuevo.
- **Publicación:** solo la rama principal, con `--force-with-lease` condicionado al commit que se esperaba, y únicamente el equivalente saneado de lo que ya estaba publicado. Después se clonó el remoto desde cero y se repitió el escaneo: mismos resultados.
- **Repositorio local:** movido a la historia nueva con `git reset --keep`, que conserva los cambios locales no relacionados.

## Procedimiento para otras máquinas

Cada clon adicional debe ejecutar `git fetch origin` y `git reset --hard origin/main` **antes** de hacer `push`, o volvería a publicar la historia antigua. Si una máquina tiene commits sin publicar, hay que trasladarlos con `git rebase --onto` o `git cherry-pick` sobre la historia nueva y no con `reset --hard`.

## Límites que hay que asumir

- La reescritura no borra copias ya hechas (clones, forks).
- GitHub puede seguir sirviendo los commits antiguos por su identificador hasta que su soporte los purgue; solo ellos pueden eliminar esos objetos.
- Los valores por defecto del código siguen en el historial (ver la tabla).

## Criterio de cierre

- Cada fila de la tabla resuelta, o descartada con la razón registrada aquí.
- Solicitud de purga a GitHub hecha o descartada de forma explícita.
- Copia de seguridad local eliminada.
