# Directrices de Agentes: {{ .AppTitle }} (`{{ .AppName }}`)

> **Guía de Ingeniería:** Si vas a modificar adaptadores, persistencia SQLite, terminal firewall o crear RFCs/ADRs, consulta [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

---

## 🛡️ 1. Invariantes Críticas

1. **Pure-Go & Concurrencia:** Compilación estricta con `CGO_ENABLED=0` y `-race` obligatorio en pruebas.
2. **Aislamiento Hexagonal:** `internal/domain/` tiene cero dependencias externas. Cero imports directos entre adaptadores.
3. **Blindaje M2M (`--json`):** `stderr` en 0 bytes; `stdout` emite JSON `ResponseEnvelope`. Códigos POSIX en [`internal/presentation/errors/envelope.go`](internal/presentation/errors/envelope.go).
4. **Terminal Firewall:** Bajo `--json` o modo no interactivo, los componentes TUI jamás deben inicializarse ni leer de `stdin`.

---

## ✅ 2. Validación y Checklist Pre-Entrega

Valida todo cambio exclusivamente mediante el `Makefile`:
1. [ ] **`make test`** pasa al 100% con `-race` (cero data races).
2. [ ] **`make docs-check`** pasa sin enlaces rotos ni inconsistencias de índice (`make docs` sincroniza índice tras RFCs/ADRs).
3. [ ] **`make build`** compila limpiamente en `bin/{{ .AppName }}` con `CGO_ENABLED=0`.
4. [ ] **`git status -s`** libre de artefactos temporales o logs (cambios de código en progreso no requieren commit).
