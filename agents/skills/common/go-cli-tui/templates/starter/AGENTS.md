# Directrices de Agentes: {{ .AppTitle }} (`{{ .AppName }}`)

> **Propósito:** Inducción técnica inmediata y salvaguardas operativas de desarrollo para agentes de IA.  
> **Guía Exhaustiva de Ingeniería:** Si vas a modificar adaptadores, persistencia SQLite, terminal firewall o crear RFCs/ADRs, es **OBLIGATORIO** leer [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) antes de editar código.

---

## ⚡ 1. Comandos Canónicos de Ciclo de Vida

Todo agente que opere en este repositorio debe validar su trabajo mediante el `Makefile`:

```bash
make test        # Suite de pruebas unitarias y de integración con race detector (-race)
make build       # Compilación estática con CGO_ENABLED=0 en bin/{{ .AppName }}
make docs-check  # Linter de consistencia de arquitectura y validación de enlaces relativos
make docs        # Sincroniza docs/INDEX.md tras crear o actualizar RFCs/ADRs
```

---

## 🛡️ 2. Reglas de Oro Innegociables (Hard Invariants)

1. **Pure-Go & Concurrencia:** Compilación estricta con `CGO_ENABLED=0`. Prohibido omitir el flag `-race` al ejecutar pruebas (`go test -race ./...`).
2. **Aislamiento Hexagonal:**
   - `internal/domain/` tiene **cero dependencias externas** (solo biblioteca estándar de Go).
   - Queda terminantemente prohibido que un adaptador dependa o importe directamente a otro adaptador.
3. **Blindaje Machine-to-Machine (`--json`):**
   - Cuando se activa el flag `--json`, `stderr` debe permanecer en **0 bytes**. Ningún log o texto plano puede contaminar `stderr`.
   - Toda salida debe emitirse por `stdout` serializada en JSON bajo el contrato `ResponseEnvelope`.
   - Códigos de salida POSIX estándar: `0` (éxito), `1` (fallo interno/no clasificado), `2` (CLI usage / datos rechazados), `3` (auth/credenciales), `4` (not found), `5` (upstream transitorio/timeout), `70` (software crash / pánico interceptado).
4. **Terminal Firewall:** En ejecuciones no interactivas o bajo `--json`, los componentes de Charm TUI nunca deben inicializarse ni leer de `stdin`.

---

## ✅ 3. Checklist Pre-Entrega

Antes de finalizar tu turno o entregar código en este repositorio:
1. [ ] **`make test`** pasa al 100% con `-race` (cero data races).
2. [ ] **`make docs-check`** pasa sin enlaces rotos ni inconsistencias de índice.
3. [ ] **`make build`** compila limpiamente en `bin/{{ .AppName }}` con `CGO_ENABLED=0`.
4. [ ] **`git status -s`** limpio de archivos temporales o no versionados.
