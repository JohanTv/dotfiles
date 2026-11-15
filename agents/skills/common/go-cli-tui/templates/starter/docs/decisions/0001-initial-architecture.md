---
id: "0001"
title: "Arquitectura Hexagonal, SQLite Pure-Go y Protocolo Dual M2M"
status: "accepted"
created: "2026-11-15"
summary: "Adopción de Go con arquitectura hexagonal limpia, persistencia SQLite sin CGO (Wazero JIT) y presentación dual (Headless M2M vs Charm TUI)."
---

# 0001 · Arquitectura Hexagonal, SQLite Pure-Go y Protocolo Dual M2M

## Contexto

El sistema requiere operar eficientemente bajo dos modos de consumo:
1. **No interactivo / M2M:** Para invocaciones desde agentes de IA (Claude Code, Gemini CLI) o pipelines de CI/CD, requiriendo JSON determinista por `stdout`, silencio en `stderr` y códigos de salida POSIX.
2. **Interactivo para humanos:** Proporcionando interfaces de terminal enriquecidas y accesibles con el framework Charm (`bubbletea`, `lipgloss`).

## Decisión

1. **Arquitectura Hexagonal:** Desacoplar el dominio puro de los adaptadores de infraestructura y presentación.
2. **Persistencia SQLite Pure-Go:** Utilizar `ncruces/go-sqlite3` con Wazero JIT (`CGO_ENABLED=0`) y aislamiento Dual-Pool WAL (1 escritor, N lectores).
3. **Cortafuegos de Terminal:** Si se detecta flag `--json`, `--plain` o ausencia de TTY, Bubble Tea nunca se instancia.

## Consecuencias

- Cero dependencias de toolchain C en el host; compilación cruzada instantánea.
- Contrato M2M estable y a prueba de roturas para agentes.
- Presentación interactiva y headless compartiendo el mismo núcleo de dominio.
