---
id: "0008"
title: Documentos de desarrollo en docs/ por tipo, con ID global y estado en la cabecera
status: aceptado
created: 2026-10-31
summary: "`docs/defects`, `docs/rfcs` y `docs/decisions`; ID `NNNN` único; estado en el front-matter; índice generado."
---

# 0008 · Documentos de desarrollo en `docs/` por tipo, con ID global y estado en la cabecera

## Contexto
`issues/` mezclaba un defecto, una propuesta y un híbrido, y `ROADMAP.md` apuntaba a ellos. Se espera que la herramienta crezca, y reorganizar después costaría más que hacerlo ahora.

## Decisión
- **Tipo por carpeta:** `docs/defects/` (lo roto), `docs/rfcs/` (lo propuesto, con alternativas) y `docs/decisions/` (lo decidido, permanente).
- **ID global único** `NNNN` en una sola secuencia. Nunca se renumera ni se reutiliza: los commits lo citan.
- **Estado en el front-matter**, nunca en la ubicación: cerrar un ítem no mueve archivos ni rompe enlaces. El estado vive solo en el documento y en el índice; los tickets de Plane no gestionan la herramienta.
- **Índice generado** (`docs/INDEX.md`) por `scripts/docs_index.py`, comprobado por `tests/test_docs.py`. Sustituye a `ROADMAP.md`.
- `docs/` no lo cita `SKILL.md`: los agentes no lo cargan.

## Alternativas descartadas
Todo en `issues/` con un campo de tipo; una carpeta plana `work-items/` (el ciclo de vida de cada tipo es distinto y el nombre choca con el vocabulario de Plane); carpetas por estado (cada cierre rompería enlaces); separar la skill del proyecto (no compensa hoy).

## Consecuencias
- Solo los estados `implementado` (RFC) y `corregido` (defecto) autorizan a citar algo como existente en el código.
- Reclasificar un ítem es un `git mv` que conserva el ID.
