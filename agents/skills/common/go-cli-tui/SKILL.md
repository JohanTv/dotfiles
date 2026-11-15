---
name: go-cli-tui
description: Guía de arquitectura, diseño SOLID y patrones de desarrollo para herramientas CLI/TUI modernas en Go con el ecosistema Charm (Bubble Tea, Lip Gloss, Bubbles, Huh). Úsalo al diseñar, implementar o refactorizar aplicaciones de terminal en Go que requieran operación dual (CLI headless estructurado para agentes de IA/CI y TUI interactiva para humanos).
---

# Skill: Arquitectura de Sistemas CLI & TUI en Go (`go-cli-tui`)

Esta habilidad condensa los estándares de ingeniería de software, arquitectura limpia (Hexagonal / Ports & Adapters) y patrones de diseño para construir herramientas de línea de comandos en **Go** que combinan **máxima ergonomía interactiva (TUI)** con **cero fricción para agentes autónomos de IA y scripts (Headless CLI)**.

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
2. **OCP (Open/Closed) & DIP (Dependency Inversion):**
   - Las capacidades especializadas (como orquestadores de workspaces Git o adaptadores de trackers externos) se implementan como módulos enchufables (`CommandModule`). Pueden operar como subcomandos integrados en el binario principal o compilarse como subherramientas CLI independientes sin modificar el núcleo.
3. **ISP (Interface Segregation):**
   - **Regla Go:** Las interfaces pertenecen al paquete consumidor, no al paquete que las implementa.
   - Interfaces pequeñas y atómicas (1 a 3 métodos): `IssueReader`, `WorklogPusher`, `WorkspaceManager`.

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
