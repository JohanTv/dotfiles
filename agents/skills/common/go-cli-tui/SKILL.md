---
name: go-cli-tui
description: Guía de arquitectura, diseño SOLID y patrones de desarrollo para herramientas CLI/TUI modernas en Go con el ecosistema Charm (Bubble Tea, Lip Gloss, Bubbles, Huh). Úsalo al diseñar, implementar o refactorizar aplicaciones de terminal en Go que requieran operación dual (CLI headless estructurado para agentes de IA/CI y TUI interactiva para humanos).
---

# Skill: Arquitectura de Sistemas CLI & TUI en Go (`go-cli-tui`)

## 1. El Principio Fundamental: Dualidad Innegociable (Headless vs TUI)

Toda herramienta moderna de ingeniería tiene dos tipos de usuarios de primera clase:
1. **Agentes de IA y Pipelines de CI:** Requieren ejecución no interactiva, determinista, salida limpia `--json` sin secuencias de escape ANSI (`\x1b`), códigos de salida estándar (POSIX) y manejo estricto de timeouts.
2. **Desarrolladores Humanos:** Requieren interfaces ricas, navegación por teclado, paneles divididos, feedback visual y formularios interactivos accesibles.

### Regla de Oro del Cortafuegos de Terminal:
```go
// Si se solicita JSON o la salida no es una terminal interactiva (TTY),
// Bubble Tea NUNCA debe instanciarse ni tocar stdout/stdin.
if isJSON || isPlain || !term.IsTerminal(int(os.Stdout.Fd())) {
    presenter.RenderHeadless(ctx, result)
    return
}
presenter.LaunchTUI(ctx, result)
```

---

## 2. Directrices Normativas SOLID en Go

- **SRP:** El dominio (`domain/`) desconoce el formato de salida; `presentation/` solo traduce modelos sin computar reglas de negocio.
- **OCP:** Extiende formatos o subcomandos mediante estrategias/módulos enchufables (`CommandModule`) sin mutar el núcleo existente.
- **LSP:** Toda implementación de puerto (`InMemoryStore`, `SQLiteStore`) respeta los contratos sin efectos colaterales imprevistos.
- **ISP:** Define interfaces pequeñas y atómicas (1 a 3 métodos: `IssueReader`, `WorkspaceManager`) en el paquete consumidor, nunca en el proveedor.
- **DIP:** Los casos de uso dependen de abstracciones (`ports/`), nunca de infraestructura (`os/exec`, `database/sql`). Inyección manual en `bootstrap/container.go`.

---

## 3. Estructura Canónica de Carpetas (Standard Go Layout)

```text
app/
├── cmd/app/main.go             # Entrypoint principal (CLI unificado)
├── internal/
│   ├── bootstrap/container.go  # Composition root / inyección manual (<5ms)
│   ├── domain/                 # Entidades y reglas puras (CERO imports de I/O)
│   ├── ports/in/, out/         # Interfaces segregadas para casos de uso y drivers
│   ├── adapters/               # Drivers concretos (sqlite/ Wazero, gitcli/ os.exec)
│   ├── presentation/           # json/ (agentes), plain/ (pipes), tui/ (Charm)
│   └── testutil/               # Fakes en memoria y sandboxes efímeros
├── testdata/golden/            # Golden files para validar salida de LLMs
└── go.mod, Makefile
```

---

## 4. Stack Tecnológico de Referencia

| Dominio | Tecnología | Justificación Técnica |
| :--- | :--- | :--- |
| **TUI Framework** | Charm (`bubbletea`, `lipgloss`, `huh`) | Estándar TEA (Model/Update/View), estilos CSS-like, formularios accesibles. |
| **Base de Datos** | `ncruces/go-sqlite3` (Wazero JIT) | **Cero CGO (`CGO_ENABLED=0`)**, compilación estática cruzada, soporte FTS5 y WAL. |
| **Concurrencia DB** | Dual-Pool WAL | Escritura `MaxOpenConns=1`, lectura `NumCPU*2` (`PRAGMA query_only=ON`). |
| **Orquestación Git** | `os/exec` sobre `git` host | Soporte nativo de `git worktree` y `git merge-tree`, aislamiento POSIX (`Setpgid`). |
| **CLI Parser** | `spf13/cobra` | Jerarquía `<grupo> <verbo>`, flags `--json`/`--plain`, autocompletado shell nativo. |

---

## 5. Estrategia de Pruebas (Testing Harness)

1. **Table-Driven Tests:** Obligatorios para la lógica pura de dominio (`domain/`).
2. **SQLite Efímero (`file:test_mem?mode=memory&cache=shared`):** Pruebas de integración en RAM en <20ms con `SetMaxOpenConns(1)`.
3. **Sandboxes Git Aislados (`t.TempDir()`):** Mutaciones de ramas y worktrees en directorios efímeros aislados.
4. **Golden File Testing:** Comparación de salida JSON contra plantillas en `testdata/golden/*.json` para proteger contratos LLM.
5. **Headless TUI Testing (`teatest`):** Simulación de teclas y mensajes al bucle de Bubble Tea sin terminal interactiva.

---

## 6. Protocolo Canónico de Errores Estructurados para Agentes de IA (`ResponseEnvelope`)

Para herramientas en modo dual (`--json`), la gestión de errores es una interfaz de comunicación máquina a máquina (M2M) entre el proceso Go y el planificador del Agente de IA (Claude Code, Gemini CLI, OpenCode):

### Reglas Inquebrantables de la Salida Estructurada:
1. **Canal Exclusivo `stdout`:** En modo `--json`, `stdout` es el único canal para el JSON Envelope (éxito y error). `stderr` debe permanecer en silencio absoluto (0 bytes) ante fallos de validación o de negocio para no romper pipelines Unix (`$()`, `| jq`).
2. **Sincronía de Códigos POSIX:** Prohibido retornar código `0` ante un error de negocio (`{"ok": false}`). Retornar siempre código de salida `!= 0` junto con `"ok": false`.
3. **Campos de Auto-Reparación (Self-Healing Loop):** `code` (inmutable en `SCREAMING_SNAKE_CASE`), `category` (`user_input` | `state_conflict` | `auth` | `upstream_service` | `internal`), `target` (argumento/entidad culpable), `hint` (sugerencia en lenguaje natural), `suggested_command` (invocación corregida) y `recoverable` (booleano).

### Especificación del Esquema JSON (`ResponseEnvelope`):

```json
{
  "ok": false,
  "error": {
    "code": "EXECUTION_ERROR",
    "category": "user_input",
    "message": "Descripción legible del error",
    "target": "--flag",
    "hint": "Instrucción de corrección inmediata",
    "suggested_command": "app comando --flag valor",
    "recoverable": true,
    "context": {}
  },
  "data": null
}
```

### Tabla de Códigos de Salida POSIX Semánticos:

| Código | Constante Go | Categoría / Significado Semántico |
| :--- | :--- | :--- |
| `0` | `ExitSuccess` | Ejecución exitosa (`ok: true`). |
| `1` | `ExitGeneralError` | Fallo general de ejecución o fallback por defecto. |
| `2` | `ExitUsageError` | Error de sintaxis, argumentos faltantes o banderas inválidas (`user_input`). |
| `3` | `ExitAuthError` | Fallo de autenticación, token ausente o permisos denegados (`auth`). |
| `4` | `ExitNotFound` | Entidad, recurso, ticket o archivo no encontrado. |
| `5` | `ExitTransientError` | Error de red o servicio upstream reintentable (`upstream_service`). |
| `70` | `ExitSoftwareError` | Fallo interno o pánico no controlado recuperado (`internal` / `INTERNAL_PANIC`). |

### Implementación en Código Go:
La implementación canónica completa (definición de estructuras, `EmitError` y resiliencia con `recover()` defensivo en `SafeExecute`) se encuentra desacoplada en:  
👉 [envelope.go](file:///home/johantv/Code/dotfiles/agents/skills/common/go-cli-tui/references/envelope.go)

---

## 7. Resiliencia Operativa y Ciclo de Vida

### A. Propagación de Contexto y Cancelación Graciosa (*Graceful Shutdown*)
Toda operación con estado (SQLite, Git, I/O) debe abortar de inmediato sin corromper datos ni dejar locks residuales (`.git/index.lock`, SQLite WAL):
```go
ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()
if err := rootCmd.ExecuteContext(ctx); err != nil { /* rollback & clean exit */ }
```
- Toda función de I/O o base de datos recibe `ctx context.Context`. Si `ctx.Err() != nil`, aborta y ejecuta rollback.

### B. Aislamiento de Subprocesos Externos (`os/exec`)
Aislar procesos secundarios en su propio Process Group para evitar zombies o bloqueos si el contexto expira:
```go
cmd := exec.CommandContext(ctx, "git", args...)
cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} // Terminar todo el PGID al cancelar
```

### C. Seguridad en Mutaciones (*CQS & Safe by Default*)
- **CQS:** Consultas (`get`, `list`, `search`, `status`) son estrictamente idempotentes y sin efectos colaterales; comandos mutan estado.
- **Dry-Run por Defecto:** Operaciones destructivas simulan la acción y exigen confirmación o banderas explícitas (`--execute`, `--force`, `--yes`).
- **Prevalencia:** Banderas CLI > Variables de Entorno (`APP_*`) > Archivo de Configuración > Defaults.

### D. TUI No Bloqueante en Bubble Tea (`tea.Cmd`)
- `Update(msg tea.Msg)` debe ser 100% síncrono e instantáneo (<16ms).
- Todo I/O, consulta SQLite o comando Git se ejecuta en goroutine asíncrona retornando un `tea.Cmd`.

---

## 8. Matriz de Madurez y Mínimos Viables (Definition of Done)

Para determinar qué tanto implementar según el escenario:

| Nivel de Herramienta | Escenario Típico | Aspectos Mínimos Recomendados |
| :--- | :--- | :--- |
| **Nivel 1: Micro-CLI** | Filtro de texto, conversor rápido, script de utilidad | Flags estándar con `cobra`, salida limpia (`stdout`), códigos de salida POSIX estándar. |
| **Nivel 2: CLI Intermedio / M2M** | Integraciones CI/CD, herramientas consumidas por Agentes de IA | Protocolo dual (`--json` con `ResponseEnvelope` canónico y auto-reparación), `SafeExecute` con `recover()`, sin secuencias ANSI en pipes. |
| **Nivel 3: Estación Autónoma / TUI** | Herramientas con estado local, orquestadores Git, dashboards | Arquitectura Hexagonal completa, Pure-Go SQLite (`ncruces/go-sqlite3`), Graceful Shutdown, Charm TUI asíncrona, sandboxes de testing efímeros (`t.TempDir()`). |
