---
name: go-cli-tui
description: Guía de arquitectura, diseño SOLID y patrones de desarrollo para herramientas CLI/TUI modernas en Go con Charm (Bubble Tea, Lip Gloss) y SQLite Wazero. Incluye scaffolding automatizado y protocolo dual headless M2M. Úsalo al diseñar, implementar o refactorizar aplicaciones de terminal en Go.
---

# Skill: Arquitectura de Sistemas CLI & TUI en Go (`go-cli-tui`)

## 1. Quickstart: Scaffolding en 5 Segundos
Para iniciar un nuevo proyecto con arquitectura hexagonal limpia, protocolo M2M, SQLite WAL y TUI:
```bash
go run ~/.agents/skills/go-cli-tui/scripts/scaffold.go \
  --name <nombre-app> \
  --module <go-module-path> \
  --target <directorio-destino>
```
*Opciones:* `--minimal` (omite TUI, solo CLI/M2M), `--description "texto"`, `--title "Título"`.

---

## 2. Principio Canónico: Dualidad Innegociable (Headless vs TUI)
Toda herramienta moderna en Go opera en dos modos mutuamente excluyentes:
1. **Modo M2M / CI / Agentes (`--json`, `--plain` o `!term.IsTerminal`):** Salida estructurada limpia en `stdout` (`ResponseEnvelope`), `stderr` en 0 bytes, códigos de salida POSIX semánticos, sin secuencias ANSI. Bubble Tea NUNCA debe inicializarse.
2. **Modo Humano / TTY:** Interfaces interactivas Charm (`bubbletea`), estilos (`lipgloss`), formularios (`huh`).

```go
// Cortafuegos de Terminal
if isJSON || isPlain || !term.IsTerminal(int(os.Stdout.Fd())) {
    presenter.RenderHeadless(ctx, result)
    return
}
presenter.LaunchTUI(ctx, result)
```

---

## 3. Matriz de Arquitectura Hexagonal Canónica
- `cmd/<app>/`: Entrypoint, Cobra CLI, Graceful Shutdown (`signal.NotifyContext`).
- `cmd/docgen/`: Generador y linter documental soberano en Go (`make docs`, `make docs-check`).
- `internal/domain/`: Entidades y lógica pura (**CERO** imports de I/O, SQL o presentación).
- `internal/ports/`: Interfaces segregadas (`in/` para casos de uso, `out/` para repositorios/drivers).
- `internal/adapters/`:
  - `storage/sqlite/`: SQLite Pure-Go (`ncruces/go-sqlite3`), WAL, Dual-Pool (1 escritor, N lectores).
- `internal/presentation/`:
  - `errors/`: `ResponseEnvelope`, códigos POSIX, `SafeExecute` defensivo con `recover()`.
  - `json/`, `plain/`: Renderizadores headless deterministas para tuberías y LLMs.
  - `tui/`: Bucle reactivo Bubble Tea v2 con comandos asíncronos (`tea.Cmd`).
- `internal/bootstrap/`: Inyección de dependencias manual (`container.go`, arranque <5ms).

---

## 4. Protocolo M2M de Errores y Códigos POSIX
- En `--json`, retornar SIEMPRE exit code != 0 ante fallos (`ok: false`):
  - `0`: Éxito | `1`: Error general | `2`: Argumentos inválidos (`user_input`) | `3`: Auth | `4`: Not Found | `5`: Error transitorio | `70`: Pánico recuperado (`internal`).
- Envolver ejecuciones CLI con `SafeExecute(jsonMode, fn)` para atrapar panics con código 70.
- `stdout` es exclusivo para el JSON; `stderr` debe permanecer en 0 bytes.

---

## 5. Referencias de Profundización (Progressive Disclosure)
Consulta estas especificaciones bajo demanda cuando implementes o audites subsistemas:
- **Protocolo M2M & Auto-Reparación:** 👉 [m2m-envelope.md](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/m2m-envelope.md)
- **Implementación Go de ResponseEnvelope:** 👉 [envelope.go](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/envelope.go)
- **Persistencia SQLite Wazero (Pure-Go WAL):** 👉 [sqlite-wazero.md](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/sqlite-wazero.md)
- **Patrones Reactivos Charm TUI (Asincronía & Layouts):** 👉 [charm-patterns.md](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/charm-patterns.md)
- **Motor Documental Soberano (`docgen` & CI):** 👉 [docgen-engine.md](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/docgen-engine.md)
- **Código Fuente de la Plantilla Starter:** 👉 [templates/starter/](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/templates/starter/)
