# Documentación de desarrollo

Aquí vive lo que se decide y se discute sobre la herramienta. Los agentes no cargan esta carpeta: `SKILL.md` no la cita. Lo operativo (cómo se usa) vive en [`../references/`](../references/README.md).

- **Índice con estado de cada documento:** [INDEX.md](./INDEX.md) (generado).
- **Principios de diseño:** [principles.md](./principles.md).
- **Por qué esta estructura:** [0008](./decisions/0008-estructura-de-docs-por-tipo-con-id-global/README.md).
- **Qué no puede aparecer aquí (el repositorio es público):** [0007](./decisions/0007-documentos-agnosticos-de-instancia.md).

## Tipos

| Carpeta | Responde a | Ciclo de vida |
| :--- | :--- | :--- |
| `defects/` | ¿Qué está roto o sin verificar? | `abierto` → `corregido` \| `descartado` |
| `rfcs/` | ¿Qué podríamos construir, con qué alternativas? | `borrador` → `propuesto` → `aceptado` → `implementado` \| `rechazado` \| `reemplazado` |
| `decisions/` | ¿Qué decidimos y por qué? | `aceptado` \| `reemplazado` |

Si un ítem es a la vez defecto y decisión (como lo fue el 0003), se parte en dos documentos enlazados.

## Reglas

1. **Nombre:** `NNNN-slug-en-minusculas.md`. El `NNNN` es único en todas las carpetas, nunca se renumera ni se reutiliza (los commits lo citan).
   **Un ítem con varios documentos relacionados** (análisis, maquetas, alternativas, mediciones) es una carpeta `NNNN-slug/`: su `README.md` es la entrada, lleva el front-matter y enlaza al resto; los demás documentos de la carpeta no llevan front-matter. Cualquier agente nuevo debe poder entender el problema leyendo esa carpeta.
2. **Front-matter obligatorio** (en el archivo del ítem o en el `README.md` de su carpeta), YAML plano:
   ```yaml
   ---
   id: "0009"
   title: Título corto
   status: borrador
   created: 2026-10-31
   summary: Una línea para el índice.
   ---
   ```
   El tipo sale de la carpeta; no se duplica. No se añade `ticket`: Plane no gestiona la herramienta.
3. **El estado se cambia en la cabecera**, no moviendo el archivo. Solo `implementado` (RFC) y `corregido` (defecto) autorizan a citar algo como existente en el código.
4. **Reclasificar** un ítem es un `git mv` que conserva el `NNNN`.
5. **Sin datos de instancia ni de personas** (hosts, IPs, workspaces, nombres, clientes): usa roles y valores de ejemplo.
6. **Tras crear o editar un documento**, regenera el índice: `python3 scripts/docs_index.py`. `tests/test_docs.py` falla si falta algo o el índice está desfasado.

## Cuándo archivar

No se archiva nada hasta tener unos 150 documentos cerrados. Entonces el índice ocultará los cerrados por defecto y, si hace falta, se moverán a `docs/<tipo>/archive/` con `git mv`; el test aceptará ambas rutas.
