---
name: go-cli-tui
description: Guía de arquitectura, diseño SOLID y patrones de desarrollo para herramientas CLI/TUI modernas en Go con el ecosistema Charm (Bubble Tea, Lip Gloss, Bubbles, Huh). Úsalo al diseñar, implementar o refactorizar aplicaciones de terminal en Go que requieran operación dual (CLI headless estructurado para agentes de IA/CI y TUI interactiva para humanos).
---

# Skill: Arquitectura de Sistemas CLI & TUI en Go (`go-cli-tui`)

> **Naturaleza de esta Habilidad:** Esta guía constituye un **catálogo de recomendaciones, patrones de diseño y aspectos mínimos a considerar** para el desarrollo de herramientas de línea de comandos en Go. No busca imponer un sobre-diseño (*over-engineering*) ni una estructura dogmática innecesaria para utilidades pequeñas: su objetivo es visibilizar las decisiones críticas de arquitectura para que, según el escenario específico (desde un micro-CLI atómico hasta una estación de trabajo completa con base de datos local y TUI), se adopten gradualmente los patrones más pertinentes con solidez.

---

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

## 2. Principios SOLID Aplicados a Go

1. **SRP (Single Responsibility):**
   - El núcleo de negocio (dominio) desconoce si la salida será un JSON, una tabla o una ventana de Bubble Tea.
   - La capa de presentación (`presentation/`) solo traduce eventos; no contiene lógica de negocio ni cálculos matemáticos.
2. **OCP (Open/Closed):**
   - Nuevos formatos de salida (Markdown, CSV, JSON) o nuevos subcomandos se agregan implementando nuevas estrategias o módulos enchufables (`CommandModule`) sin tener que modificar el núcleo existente.
3. **LSP (Liskov Substitution):**
   - Cualquier implementación de un puerto (por ejemplo, un `InMemoryStore` para pruebas y un `SQLiteStore` para producción) es 100% intercambiable sin alterar las garantías ni el comportamiento esperado por los casos de uso.
4. **ISP (Interface Segregation):**
   - **Regla Go:** Las interfaces pertenecen al paquete consumidor (donde se usan), no al paquete que las implementa.
   - Interfaces pequeñas y atómicas (1 a 3 métodos): `IssueReader`, `WorklogPusher`, `WorkspaceManager`.
5. **DIP (Dependency Inversion):**
   - Los casos de uso de alto nivel nunca importan directamente drivers de bajo nivel (`os/exec`, `database/sql`, `net/http`). Ambos dependen de abstracciones (puertos). La inyección y composición de dependencias se realiza exclusivamente en el arranque (`main.go` / `bootstrap`).

---

## 3. Estructura Canónica de Carpetas (Standard Go Project Layout)

```text
app/
├── cmd/
│   ├── app/                    # Entrypoint principal (CLI unificado)
│   │   └── main.go
│   └── app-subtool/            # Entrypoint alternativo standalone (opcional)
│       └── main.go
│
├── internal/
│   ├── bootstrap/              # Composition Root: inyección manual explícita (arranque <5ms)
│   │   └── container.go
│   │
│   ├── domain/                 # 🧠 Entidades, Value Objects, Agregados (CERO imports de I/O)
│   │
│   ├── ports/                  # 🔌 Interfaces segregadas (in/ para use cases, out/ para drivers)
│   │   ├── in/
│   │   └── out/
│   │
│   ├── adapters/               # ⚙️ Infraestructura y drivers concretos
│   │   ├── sqlite/             # Pure-Go SQLite (ncruces/go-sqlite3)
│   │   │   └── migrations/     # //go:embed *.sql
│   │   └── gitcli/             # Wrapper os/exec con PGID isolation y feature detection
│   │
│   ├── presentation/           # 🖥️ Estrategias de salida
│   │   ├── json/               # Presenter JSON estructurado para IA/scripts
│   │   ├── plain/              # Presenter para tuberías Unix
│   │   └── tui/                # 🌸 Ecosistema Charm (The Elm Architecture)
│   │       ├── app.go          # Modelo raíz de Bubble Tea
│   │       ├── styles.go       # Lip Gloss
│   │       ├── views/          # Pantallas y formularios (Huh)
│   │       └── components/     # Tablas y listas (Bubbles)
│   │
│   └── testutil/               # Fakes en memoria y sandboxes efímeros de prueba
│
├── testdata/                   # Archivos dorados (Golden files para salidas CLI)
│   └── golden/
├── go.mod
├── go.sum
└── Makefile
```

---

## 4. Decisiones de Stack Tecnológico de Referencia

| Dominio | Tecnología Recomendada | Justificación Técnica |
| :--- | :--- | :--- |
| **TUI Framework** | **Charm Ecosystem** (`bubbletea`, `lipgloss`, `bubbles`, `huh`, `glamour`) | Estándar de la industria. Arquitectura TEA (Model, Update, View), tipografía y estilos CSS-like, componentes accesibles y renderizado Markdown nativo. |
| **Base de Datos** | **`ncruces/go-sqlite3`** (Wazero JIT) | **Cero CGO (`CGO_ENABLED=0`)**, compilación estática cruzada inmediata. Soporte completo de **FTS5**, triggers, modo WAL y rendimiento casi indistinguible de CGO sin saturar el GC. |
| **Control Concurrente DB** | **Dual-Pool en Modo WAL** | Pool de escritura con `MaxOpenConns = 1` y pool de lectura con `MaxOpenConns = NumCPU * 2` (`PRAGMA query_only = ON`), erradicando bloqueos de base de datos. |
| **Orquestación Git** | **`os/exec` sobre binario `git` del host** | `go-git` carece de soporte para `git worktree` y `git merge-tree --write-tree`. Usar el binario del host con aislamiento POSIX (`Setpgid: true`) y detección de versión SemVer. |
| **CLI Parser** | **`spf13/cobra`** | Jerarquía robusta `<grupo> <verbo>`, soporte de alias, autocompletado de shell nativo e integración limpia con flags `--json` y `--plain`. |

---

## 5. Estrategia y Entorno de Pruebas (Testing Harness)

1. **Table-Driven Tests:** Obligatorios para todos los algoritmos del dominio (`domain/`), con pruebas parametrizadas en estructuras anónimas.
2. **SQLite Efímero (`file:test_mem?mode=memory&cache=shared`):** Pruebas de integración de base de datos ejecutadas en memoria RAM en <20ms por suite fijando `SetMaxOpenConns(1)`.
3. **Sandboxes Git Aislados (`t.TempDir()`):** Pruebas de mutación de ramas o worktrees ejecutadas exclusivamente dentro de directorios temporales gestionados por Go.
4. **Golden File Testing para Agentes:** Pruebas que comparan la salida JSON del CLI contra plantillas en `testdata/golden/*.json` para garantizar que ningún cambio rompa los contratos de los LLMs.
5. **Headless TUI Testing (`teatest`):** Uso de `github.com/charmbracelet/x/exp/teatest` para enviar mensajes y pulsaciones de teclas simuladas al bucle de Bubble Tea y verificar el modelo final sin abrir terminal interactiva.

---

## 6. Protocolo Canónico de Errores Estructurados para Agentes de IA (`ResponseEnvelope`)

Para herramientas en modo dual (`--json`), la gestión de errores es una **interfaz de comunicación M2M (Máquina a Máquina)** entre el proceso Go y el planificador del Agente de IA (Claude Code, Gemini CLI, OpenCode):

### Reglas Inquebrantables de la Salida Estructurada:
1. **Canal Exclusivo `stdout`:**  
   - En modo `--json`, **`stdout` es el único canal para el JSON Envelope** (tanto en éxito como en fallo).
   - `stderr` debe permanecer en **silencio absoluto (0 bytes)** durante errores de validación y de negocio para no romper pipelines Unix (`$()`, `| jq`).
2. **Sincronía de Códigos POSIX:**  
   - Prohibido devolver código de salida `0` ante un error de negocio (`{"ok": false}`). El planificador del LLM interpretaría `0` como éxito.
   - Retornar **código de salida != 0** junto con `"ok": false` en el payload JSON.
3. **Campos de Auto-Reparación (Self-Healing Loop):**  
   - `code`: Identificador inmutable en `SCREAMING_SNAKE_CASE`.
   - `category`: `user_input` | `state_conflict` | `auth` | `upstream_service` | `internal`.
   - `target`: Argumento, flag o entidad culpable exacta (ej. `--base`, `duration`).
   - `hint`: Sugerencia concisa en lenguaje natural para que el modelo no tenga que consultar docs.
   - `suggested_command`: Invocación corregida lista para ejecutarse en el siguiente turno.
   - `recoverable`: Booleano que indica si un reintento tiene sentido o debe detenerse.

### Estructura Canónica de Go (`internal/presentation/errors/envelope.go`):

```go
package errors

import (
	"encoding/json"
	"fmt"
	"os"
)

type ErrorCategory string

const (
	CategoryUserInput       ErrorCategory = "user_input"
	CategoryStateConflict   ErrorCategory = "state_conflict"
	CategoryAuth            ErrorCategory = "auth"
	CategoryUpstreamService ErrorCategory = "upstream_service"
	CategoryInternal        ErrorCategory = "internal"
)

// Códigos POSIX semánticos
const (
	ExitSuccess       = 0
	ExitGeneralError  = 1
	ExitUsageError    = 2
	ExitAuthError     = 3
	ExitNotFound      = 4
	ExitTransientError= 5
	ExitSoftwareError = 70 // EX_SOFTWARE
)

type ErrorDetail struct {
	Code             string                 `json:"code"`
	Category         ErrorCategory          `json:"category"`
	Message          string                 `json:"message"`
	Target           string                 `json:"target,omitempty"`
	Hint             string                 `json:"hint,omitempty"`
	SuggestedCommand string                 `json:"suggested_command,omitempty"`
	Recoverable      bool                   `json:"recoverable"`
	Context          map[string]interface{} `json:"context,omitempty"`
}

type ResponseEnvelope struct {
	OK    bool         `json:"ok"`
	Error *ErrorDetail `json:"error,omitempty"`
	Data  interface{}  `json:"data,omitempty"`
}

// EmitError emite el error estructurado a stdout cuando jsonMode está activo
func EmitError(err error, detail ErrorDetail, exitCode int, jsonMode bool) {
	if exitCode == 0 {
		exitCode = ExitGeneralError
	}
	if detail.Code == "" {
		detail.Code = "EXECUTION_ERROR"
	}
	if detail.Category == "" {
		detail.Category = CategoryUserInput
	}
	if detail.Message == "" && err != nil {
		detail.Message = err.Error()
	}

	if jsonMode {
		env := ResponseEnvelope{
			OK:    false,
			Error: &detail,
		}
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(env)
		os.Exit(exitCode)
	}

	// Salida interactiva para humanos por stderr
	fmt.Fprintf(os.Stderr, "✖ Error [%s]: %s\n", detail.Code, detail.Message)
	if detail.Hint != "" {
		fmt.Fprintf(os.Stderr, "💡 Sugerencia: %s\n", detail.Hint)
	}
	if detail.SuggestedCommand != "" {
		fmt.Fprintf(os.Stderr, "👉 Ejecuta: %s\n", detail.SuggestedCommand)
	}
	os.Exit(exitCode)
}
```

### Resiliencia ante Panics en el Entrypoint (`SafeExecute`):
Envolver la ejecución del CLI con un `recover()` defensivo para garantizar que un panic inesperado nunca escape como stack trace de texto plano cuando `--json` esté activo, emitiendo en su lugar un `code: "INTERNAL_PANIC"` con código de salida `70`.

---

## 7. Resiliencia Operativa y Ciclo de Vida (Aspectos Clave por Escenario)

Dependiendo de si la herramienta realiza mutaciones en disco, maneja subprocesos externos o levanta una interfaz TUI interactiva, considera las siguientes recomendaciones técnicas:

### A. Propagación de Contexto y Cancelación Graciosa (*Graceful Shutdown*)
Si la herramienta realiza operaciones con estado (escrituras en SQLite, orquestación Git, transferencias de archivos), presionar `Ctrl+C` (`SIGINT`) o recibir `SIGTERM` no debe corromper los datos ni dejar bloqueos colgados (`.git/index.lock` o SQLite WAL abiertos):

```go
// En cmd/main.go:
ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()

if err := rootCmd.ExecuteContext(ctx); err != nil {
    // Manejo de salida ordenada
}
```
- Toda función de I/O, red o base de datos debe recibir `ctx context.Context`.
- Si `ctx.Err() != nil`, abortar inmediatamente y disparar rutinas de *rollback* o *cleanup*.

### B. Aislamiento y Control de Subprocesos Externos (`os/exec`)
Al invocar comandos del sistema (como `git` o herramientas auxiliares), un timeout o cancelación debe terminar a toda la jerarquía de procesos para evitar procesos zombies o bloqueos residuales:

```go
cmd := exec.CommandContext(ctx, "git", args...)
// En sistemas POSIX: aislar en su propio Process Group
cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

// En caso de cancelación forzosa por timeout, matar el grupo completo:
// syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
```

### C. Seguridad en Mutaciones y Ergonomía (*Safe by Default & CQS*)
- **Separación de Comandos y Consultas (CQS):** Una lectura (`get`, `list`, `search`, `status`) NUNCA debe producir efectos colaterales ni mutar el estado.
- **Dry-Run por Defecto:** Cualquier operación destructiva (poda masiva de archivos, borrado de ramas, sobreescritura) debe simularse por defecto y exigir confirmación o banderas explícitas (`--execute`, `--force`, `--yes`).
- **Jerarquía de Prevalencia de Configuración:**  
  `Banderas CLI` > `Variables de Entorno` (`APP_*`) > `Archivo de Configuración` (`~/.config/app/config.json`) > `Valores por Defecto`.

### D. TUI No Bloqueante en Bubble Tea (`tea.Cmd`)
- **Regla Inquebrantable:** El método `Update(msg tea.Msg)` del bucle de Bubble Tea debe ser 100% síncrono y retornar de inmediato.
- **I/O Asíncrono:** Cualquier consulta a base de datos, llamada de red o comando Git debe envolverse en un `tea.Cmd` para ejecutarse en una goroutine separada. De lo contrario, la interfaz se congelará, perdiendo la fluidez de 60 FPS y bloqueando los spinners de carga.

---

## 8. Matriz de Madurez y Mínimos Viables (Definition of Done)

Para determinar qué tanto implementar según el escenario:

| Nivel de Herramienta | Escenario Típico | Aspectos Mínimos Recomendados |
| :--- | :--- | :--- |
| **Nivel 1: Micro-CLI** | Filtro de texto, conversor rápido, script de utilidad | Flags estándar con `cobra`, salida limpia (`stdout`), códigos de salida POSIX estándar. |
| **Nivel 2: CLI Intermedio / M2M** | Integraciones CI/CD, herramientas consumidas por Agentes de IA | Protocolo dual (`--json` con `ResponseEnvelope` canónico y auto-reparación), `SafeExecute` con `recover()`, sin secuencias ANSI en pipes. |
| **Nivel 3: Estación Autónoma / TUI** | Herramientas con estado local, orquestadores Git, dashboards | Arquitectura Hexagonal completa, Pure-Go SQLite (`ncruces/go-sqlite3`), Graceful Shutdown, Charm TUI asíncrona, sandboxes de testing efímeros (`t.TempDir()`). |
