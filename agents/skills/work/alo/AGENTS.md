# Directrices de Agentes: Allostasis (`alo`)

> **Propósito:** Inducción técnica inmediata y salvaguardas operativas de desarrollo para agentes de IA.  
> **Guía Exhaustiva de Ingeniería:** Si vas a modificar adaptadores, persistencia SQLite, subprocesos Git o crear RFCs/ADRs, es **OBLIGATORIO** leer [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) antes de editar código.

---

## ⚡ 1. Comandos Canónicos de Ciclo de Vida

Todo agente que opere en este repositorio debe validar su trabajo mediante el `Makefile`:

```bash
make test        # Suite de pruebas unitarias y de integración con race detector (-race)
make build       # Compilación estática con CGO_ENABLED=0 en bin/alo
make docs-check  # Linter de consistencia de arquitectura y validación de enlaces relativos
make docs        # Sincroniza docs/INDEX.md tras crear o actualizar RFCs/ADRs
```

---

## 🛡️ 2. Reglas de Oro Innegociables (Hard Invariants)

1. **Pure-Go & Concurrencia:** Compilación estricta con `CGO_ENABLED=0`. Prohibido omitir el flag `-race` al ejecutar pruebas de repositorios o concurrencia (`go test -race ./...`).
2. **Reloj Determinista:** Prohibido usar `time.Now()` en dominio o aplicación. Usa exclusivamente la abstracción canónica [`clock.Clock`](internal/domain/clock/clock.go) (`RealClock` en prod, `FrozenClock` en tests).
3. **Aislamiento Hexagonal:**
   - `internal/domain/` tiene **cero dependencias externas** (solo biblioteca estándar de Go).
   - Queda terminantemente prohibido que un adaptador dependa o importe directamente a otro adaptador.
4. **Blindaje Machine-to-Machine (`--json`):**
   - Cuando se activa el flag `--json`, `stderr` debe permanecer en **0 bytes**. Ningún log, texto plano o traza puede contaminar `stderr`.
   - Toda salida debe emitirse por `stdout` serializada en JSON bajo el contrato `ResponseEnvelope`.
   - Códigos de salida POSIX estándar: `0` (éxito), `1` (fallo de dominio/ejecución), `2` (CLI usage), `3` (not found), `4` (conflicto/prerrequisito no cumplido).

---

## ✅ 3. Checklist Pre-Entrega

Antes de finalizar tu turno o entregar código en este repositorio:
1. [ ] **`make test`** pasa al 100% con `-race` (cero data races).
2. [ ] **`make docs-check`** pasa sin enlaces rotos ni inconsistencias de índice.
3. [ ] **`make build`** compila limpiamente en `bin/alo` con `CGO_ENABLED=0`.
4. [ ] **`git status -s`** limpio de volcados SQLite, artefactos de test o logs temporales.
