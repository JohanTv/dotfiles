---
id: "0002"
title: "Especificación de Contrato CLI y Envelope JSON v1"
status: "implemented"
created: "2026-11-15"
summary: "Definición normativa del formato ResponseEnvelope, categorías de error y códigos de salida POSIX."
---

# 0002 · Especificación de Contrato CLI y Envelope JSON v1

## Contexto

Las herramientas CLI consumidas por agentes de IA requieren formatos estructurados deterministas para éxito y error, evitando scraping no estándar de cadenas de texto.

## Propuesta

Implementar `ResponseEnvelope` como estándar de salida para `--json`:
- `ok: true` acompaña `data`.
- `ok: false` acompaña `error` con campos de auto-reparación (`code`, `category`, `message`, `target`, `hint`, `suggested_command`, `recoverable`).
- Silencio estricto en `stderr` (0 bytes) ante errores de validación.

## Consecuencias

- Agentes de IA son capaces de auto-corregir invocaciones erróneas sin intervención humana.
- Compatibilidad nativa con tuberías Unix estándar.
