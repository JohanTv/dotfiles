# Crítica Técnica, Evaluación de Runtime y Arquitectura Hexagonal Definitiva en Go para Alostasis (`alo`)

> **Documento:** Dictamen de Arquitectura de Sistemas, Evaluación de Compilador/Runtime y Especificación Hexagonal DDD  
> **Sistema Objetivo:** `Alostasis` (Alias CLI: `alo` | Repositorio: `github.com/allostasis/alo`)  
> **Fecha:** Noviembre 2026  
> **Autor:** Principal Systems Architect, Go Compiler/Runtime Specialist y DDD Lead  
> **Estado:** Aprobado como Especificación Canónica de Arquitectura  
> **Reemplaza/Enmienda:** Evaluación preliminar en `INFORME_VIABILIDAD_TECNICA_GO_Y_CHARM_TUI.md`  

---

## 1. Resumen Ejecutivo y Dictamen de Dirección Técnica

El informe técnico previo (`INFORME_VIABILIDAD_TECNICA_GO_Y_CHARM_TUI.md`) acertó en su diagnóstico general: la migración del stack actual de herramientas CLI y telemetría (`plane-tracker` y `plane-worktree`) desde Python 3 hacia **Go (Golang)** es una decisión imperativa para erradicar la fragilidad operativa de los entornos virtuales, desbloquear tiempos de respuesta sub-10ms y ofrecer interfaces interactivas de primer nivel.

Sin embargo, desde una perspectiva de **ingeniería de sistemas de misión crítica, compiladores e interfaces para agentes autónomos**, dicho informe incurrió en **simplificaciones peligrosas, asunciones ingenuas y vacíos arquitectónicos inadmisibles**:

1. **Sesgo Humano-Céntrico (El Olvido de los Agentes Autónomos):** El informe anterior dedicó un entusiasmo desmedido a las capturas y wireframes de Bubble Tea y Charm, olvidando que la herramienta es, ante todo, **la interfaz primaria de automatización para Agentes Autónomos de Inteligencia Artificial (Claude Code, Gemini CLI, subagentes de desarrollo) y scripts de CI/CD**. Si el runtime de Go inicializa Bubble Tea, emite secuencias de escape ANSI, secuestra descriptores de archivo o captura señales de terminal en un entorno headless o en un pipe (`alo issue list --json | jq`), rompe de forma catastrófica el flujo cognitivo de los agentes.
2. **Falsa Equivalencia en Drivers de SQLite:** Trató a `ncruces/go-sqlite3` y `modernc.org/sqlite` como opciones intercambiables. En la práctica de bajo nivel, representan filosofías de runtime diametralmente opuestas: un motor C compilado a WebAssembly ejecutado con compilación JIT en memoria lineal vía `wazero` frente a un transpilador de C a AST de Go con alta fragmentación de memoria y contención en bloqueos concurrentes de WAL.
3. **Fragilidad Extrema en la Invocación de Git:** Delegó la orquestación de worktrees ciegamente a `os/exec` sin contemplar la heterogeneidad de versiones de Git en los hosts (rompiéndose en versiones previas a Git 2.38 que carecen de `git merge-tree --write-tree`), sin mecanismos de aislamiento de grupos de procesos contra zombies en llamadas remotas y sin sanitización estricta frente a ataques de inyección de flags.
4. **Arquitectura Hexagonal Superficial:** Mencionó carpetas hexagonales pero omitió los contratos formales de diseño: no definió agregados inmutables, no resolvió la contención del pool de conexiones en SQLite WAL, ni especificó un *Composition Root* determinista sin frameworks reflexivos de inyección de dependencias.

El presente documento corrige de raíz estas deficiencias, estableciendo los **fundamentos de ingeniería definitivos, sin atajos ni parches**, para el desarrollo de **Alostasis (`alo`)**.

---

## 2. Auditoría Crítica e Implacable del Informe Previo

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   MATRIZ DE AUDITORÍA CRÍTICA AL INFORME PREVIO                        │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ COMPONENTE EVALUADO      │ DEFICIENCIA EN INFORME   │ CORRECCIÓN ARQUITECTÓNICA        │
│                          │ PRELIMINAR (PREVIO)      │ CANÓNICA (ESTE DOCUMENTO)        │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 1. Dualidad CLI / TUI    │ Trató TUI y CLI como una │ Patrón Presentation Strategy con │
│                          │ sola capa de interfaz;   │ detección de TTY y cortafuegos   │
│                          │ riesgo de ANSI en JSON.  │ estricto para modo Headless/IA.  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 2. Driver SQLite Pure-Go │ Homologó ncruces con     │ Selección técnica de ncruces/    │
│                          │ modernc; ignoró gestión  │ sqlite3 (Wasm/wazero); pool dual │
│                          │ de memoria y contención. │ (1 writer / N readers en WAL).   │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 3. Integración con Git   │ exec.Command plano;      │ Feature Detection en arranque;   │
│                          │ sin control de versión   │ pgid isolation contra zombies;   │
│                          │ ni flag-injection guard. │ sanitización y doble guion (--). │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 4. Hexagonal & SOLID     │ Diagrama de directorios  │ DDD canónico: Value Objects,     │
│                          │ sin agregados ni ciclo de│ Agregados puros, UoW explícito,  │
│                          │ vida de dependencias.    │ Composition Root estático (Go).  │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

### 2.1 Punto Ciego 1: El Gran Riesgo de la Inicialización de Terminales Reactivas en Pipelines de IA
El error conceptual más grave del informe preliminar fue priorizar el *renderizado estético* sobre la *inmutabilidad del stream de salida*. 
Cuando un modelo de lenguaje (LLM) ejecuta un comando mediante una herramienta de shell, espera un flujo de bytes predecible:
- Si se emite la secuencia `\x1b[?1049h` (entrada a la pantalla alterna de xterm), el agente no recibe el texto en su búfer estándar.
- Si Bubble Tea configura el terminal en modo *Raw* (`terminal.MakeRaw`), las combinaciones de teclas, interrupciones `SIGINT` y retornos de carro (`\r\n`) se desincronizan, provocando que los subprocesos de los agentes se cuelguen indefinidamente esperando eventos del teclado.
- El informe anterior no diseñó un desacoplamiento entre el caso de uso y el formateador de salida, asumiendo que los flags de CLI podían coexistir de manera informal con el bucle de eventos TEA (*The Elm Architecture*).

### 2.2 Punto Ciego 2: La Falsa Equivalencia `ncruces/go-sqlite3` vs `modernc.org/sqlite`
El informe previo afirmó textualmente: *"Se adopta ncruces/go-sqlite3 (o en su defecto modernc.org/sqlite como alternativa de compatibilidad directa)"*. Esta declaración ignora cómo opera el compilador y el recolector de basura de Go:
- `modernc.org/sqlite` es el resultado de transpilar código C a Go mediante `ccgo`. Transforma aritmética de punteros en rebanadas (`slices`) de memoria plana en el heap de Go. Esto genera una presión masiva en el Garbage Collector (GC) durante consultas intensivas sobre tablas virtuales FTS5, introduciendo pausas (*stop-the-world*) impredecibles y consumiendo hasta 3 veces más memoria que el binario C original. Además, en entornos con múltiples lecturas concurrentes y escrituras en modo WAL, ha presentado fallos de contención y corrupciones silenciosas bajo estrés de goroutines.
- `ncruces/go-sqlite3` compila el código fuente oficial de SQLite a WebAssembly y lo ejecuta mediante `wazero`. Wazero traduce el bytecode Wasm directamente a código de máquina nativo (`amd64` y `arm64`) en tiempo de carga, utilizando memoria lineal protegida fuera de la supervisión directa del GC de Go. El resultado es rendimiento casi idéntico a C nativo (~1.1x de CGO), aislamiento determinista y soporte impecable de extensiones FTS5 y triggers sin penalizar el runtime.

### 2.3 Punto Ciego 3: Confianza Ciega en `os/exec` sin Detección de Capacidades de Git
El uso de `git merge-tree --write-tree` para verificar integraciones de ramas en memoria (squash/rebase) sin tocar el árbol de trabajo fue una innovación excelente en Python. Sin embargo, su traslación a Go fue superficial:
- La bandera `--write-tree` fue incorporada en **Git 2.38** (octubre 2022). Si un desarrollador o agente de CI/CD corre en una distribución de soporte extendido (como Ubuntu 22.04 LTS con Git 2.34 nativo), el comando aborta con `error: unknown option write-tree`.
- La llamada a `os/exec.Command` sin aislamiento de grupo de procesos (`Setpgid: true`) provoca que si `git fetch` o `git ls-remote` se bloquea por un prompt de credenciales SSH o un proxy inactivo, el proceso hijo quede huérfano (zombie) consumiendo descriptores de archivo incluso tras vencer el timeout del contexto.
- Pasar argumentos directamente a Git sin un validador de inyección de flags permite que si un identificador de ticket o rama comienza con guion (ej. `--upload-pack=...`), el binario de Git lo interprete como una opción de configuración arbitraria.

---

## 3. La Dualidad Innegociable: CLI Headless (IA/Scripts) vs TUI Reactiva (Humanos)

El principio cardinal de diseño para `alo` es:
> **"Un único núcleo de dominio, dos modos de existencia mutuamente excluyentes: Headless Determinista para máquinas, TUI Inmersiva para humanos."**

```text
                               ┌───────────────────────────┐
                               │     Invocación de alo     │
                               │  (Entrada CLI / Subshell) │
                               └─────────────┬─────────────┘
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │  Decision Engine de TTY   │
                               │ • Flag --json explícito?  │
                               │ • Flag --plain?           │
                               │ • isatty(os.Stdout)?      │
                               │ • CI / NO_COLOR / TERM?   │
                               └─────────────┬─────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
         [MODO HEADLESS / MAQUINARIA]                   [MODO TUI / HUMANO]
      • Flag --json o !isatty(stdout)               • isatty(stdout) && interactivo
  ┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
  │ 1. Cortafuegos de Terminal:         │       │ 1. Inicialización de Charm:         │
  │    • tea.NewProgram NUNCA se llama  │       │    • Configuración de Raw Mode      │
  │    • Zero secuencias ANSI (\x1b)    │       │    • Alternate Screen Buffer        │
  │    • Zero alternate screen buffers  │       │    • Captura de redimensionamiento  │
  │ 2. Contexto Limpio de Señales:      │       │ 2. The Elm Architecture (TEA):      │
  │    • signal.NotifyContext nativo    │       │    • Bucle interactivo continuo     │
  │    • Retorno directo en SIGINT/TERM │       │    • Enrutamiento por submodelos    │
  │ 3. Presentation Strategy:           │       │ 3. View Strategy:                   │
  │    • JSONPresenter o PlainPresenter │       │    • TUIStrategy (Lipgloss + Bubble)│
  │    • Envoltura tipada (Envelope)    │       │    • Renderizado gráfico a 60 fps   │
  └──────────────────┬──────────────────┘       └──────────────────┬──────────────────┘
                     │                                             │
                     └──────────────────────┬──────────────────────┘
                                            │
                                            ▼
                               ┌───────────────────────────┐
                               │    Application Service    │
                               │     (Caso de Uso Puro)    │
                               └───────────────────────────┘
```

### 3.1 Detección Rigurosa del Entorno de Ejecución

El runtime no debe adivinar: debe evaluar una jerarquía matemática de condiciones para determinar el modo de presentación antes de instanciar cualquier subsistema gráfico.

```go
package ui

import (
	"os"

	"golang.org/x/term"
)

type OutputMode int

const (
	OutputModeJSON OutputMode = iota
	OutputModePlain
	OutputModeInteractiveTUI
)

type ExecutionContext struct {
	Mode         OutputMode
	IsStdoutTTY  bool
	IsStderrTTY  bool
	IsStdinTTY   bool
	ColorEnabled bool
}

// ResolveExecutionContext evalúa las condiciones del sistema de forma determinista.
func ResolveExecutionContext(jsonFlag, plainFlag, forceInteractive bool) ExecutionContext {
	stdoutFd := int(os.Stdout.Fd())
	stdinFd := int(os.Stdin.Fd())
	stderrFd := int(os.Stderr.Fd())

	isStdoutTTY := term.IsTerminal(stdoutFd)
	isStdinTTY := term.IsTerminal(stdinFd)
	isStderrTTY := term.IsTerminal(stderrFd)

	// 1. Regla Suprema: Si se pide JSON explícito, JAMÁS se abre TUI
	if jsonFlag {
		return ExecutionContext{
			Mode:         OutputModeJSON,
			IsStdoutTTY:  isStdoutTTY,
			IsStderrTTY:  isStderrTTY,
			IsStdinTTY:   isStdinTTY,
			ColorEnabled: false,
		}
	}

	// 2. Si se pide salida plana o no hay terminal conectada en stdout/stdin
	if plainFlag || !isStdoutTTY || !isStdinTTY {
		if forceInteractive && isStdoutTTY {
			// Forzado manual con bandera interactiva en terminal válida
			return ExecutionContext{
				Mode:         OutputModeInteractiveTUI,
				IsStdoutTTY:  isStdoutTTY,
				IsStderrTTY:  isStderrTTY,
				IsStdinTTY:   isStdinTTY,
				ColorEnabled: os.Getenv("NO_COLOR") == "",
			}
		}
		return ExecutionContext{
			Mode:         OutputModePlain,
			IsStdoutTTY:  isStdoutTTY,
			IsStderrTTY:  isStderrTTY,
			IsStdinTTY:   isStdinTTY,
			ColorEnabled: false,
		}
	}

	// 3. Entorno interactivo humano por defecto
	return ExecutionContext{
		Mode:         OutputModeInteractiveTUI,
		IsStdoutTTY:  isStdoutTTY,
		IsStderrTTY:  isStderrTTY,
		IsStdinTTY:   isStdinTTY,
		ColorEnabled: os.Getenv("NO_COLOR") == "",
	}
}
```

### 3.2 Patrón Presentation Strategy (`PresenterPort` y `ViewStrategy`)

Los Casos de Uso (`application`) **nunca** escriben en `os.Stdout` ni conocen a Bubble Tea. Retornan tipos de dominio puros o DTOs en una estructura `Result[T]`. La capa de presentación selecciona la estrategia correspondiente.

```go
package ports

import (
	"context"
	"io"
)

// Presenter define el contrato de renderizado independiente del canal de salida.
type Presenter[T any] interface {
	Present(ctx context.Context, data T, writer io.Writer) error
}

// JSONEnvelope estandariza la salida estructurada para agentes autónomos y scripts.
type JSONEnvelope[T any] struct {
	Version   string   `json:"version"`
	Timestamp string   `json:"timestamp"`
	Success   bool     `json:"success"`
	Data      T        `json:"data,omitempty"`
	Errors    []string `json:"errors,omitempty"`
	Metadata  Meta     `json:"metadata"`
}

type Meta struct {
	ExecutionTimeMs float64 `json:"execution_time_ms"`
	MachineReadable bool    `json:"machine_readable"`
}
```

#### Implementación del `JSONPresenter`:
Garantiza JSON estrictamente válido, sin secuencias ANSI, con indentación limpia (o compacta para agentes) y con `Success: true/false`.

```go
package presenters

import (
	"context"
	"encoding/json"
	"io"
	"time"

	"github.com/allostasis/alo/internal/ports"
)

type JSONPresenter[T any] struct {
	version string
}

func NewJSONPresenter[T any](version string) *JSONPresenter[T] {
	return &JSONPresenter[T]{version: version}
}

func (p *JSONPresenter[T]) Present(ctx context.Context, data T, writer io.Writer) error {
	envelope := ports.JSONEnvelope[T]{
		Version:   p.version,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Success:   true,
		Data:      data,
		Metadata: ports.Meta{
			MachineReadable: true,
		},
	}

	encoder := json.NewEncoder(writer)
	encoder.SetIndent("", "  ")
	encoder.SetEscapeHTML(false)
	return encoder.Encode(envelope)
}
```

#### Implementación del `TUIStrategy`:
Instancia Bubble Tea **únicamente** cuando el `ExecutionContext` es `OutputModeInteractiveTUI`. Si el usuario pulsa `q` o `Ctrl+C`, Bubble Tea restaura el terminal antes de salir, garantizando que el prompt de la shell receptora quede intacto.

```go
package presenters

import (
	"context"
	"fmt"
	"io"

	tea "github.com/charmbracelet/bubbletea"
)

type TUIStrategy[T any] struct {
	modelFactory func(initialData T) tea.Model
}

func NewTUIStrategy[T any](factory func(T) tea.Model) *TUIStrategy[T] {
	return &TUIStrategy[T]{modelFactory: factory}
}

func (s *TUIStrategy[T]) Present(ctx context.Context, data T, _ io.Writer) error {
	initialModel := s.modelFactory(data)
	program := tea.NewProgram(
		initialModel,
		tea.WithAltScreen(),
		tea.WithContext(ctx),
	)

	finalModel, err := program.Run()
	if err != nil {
		return fmt.Errorf("tui runtime failure: %w", err)
	}

	_ = finalModel
	return nil
}
```

---

## 4. Evaluación Rigurosa de SQLite en Pure-Go

Para que `alo` sea un binario estático autocontenido distribuible mediante un simple `curl | sh` o Homebrew, el compilador debe operar estrictamente con `CGO_ENABLED=0`.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   COMPARATIVA TÉCNICA DE DRIVERS SQLITE EN GO                          │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ CRITERIO                 │ modernc.org/sqlite       │ ncruces/go-sqlite3               │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Mecanismo de Ejecución   │ Transpilado C -> Go      │ SQLite original C compilado a    │
│                          │ vía ccgo (AST en Go)     │ Wasm; ejecutado con JIT (wazero) │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Dependencia de CGO       │ Zero (CGO_ENABLED=0)     │ Zero (CGO_ENABLED=0)             │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Presión sobre el GC      │ ALTA (Emulación de heap  │ NULA (Memoria lineal Wasm        │
│                          │ de C en slices de Go)    │ gestionada fuera del GC de Go)   │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Rendimiento relativo     │ ~2.5x a 3.0x más lento   │ ~1.1x a 1.25x vs C nativo        │
│ frente a C nativo        │ que C nativo             │ (Compilación JIT directa)        │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Concurrencia en modo WAL │ Problemas de contención  │ Idéntico a C nativo; bloqueo de  │
│                          │ y panics en cargas altas │ archivo POSIX determinista       │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Soporte FTS5 Completo    │ Sí, con tokenizer simple │ Completo (unicode61, diacríticos,│
│                          │                          │ stemmers y extensiones math)     │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Compilación Cruzada      │ Universal                │ Universal (JIT en amd64/arm64;   │
│                          │                          │ intérprete fallback en otros)    │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

### 4.1 Dictamen Categórico: Adopción Exclusiva de `ncruces/go-sqlite3`
Rechazamos formalmente `modernc.org/sqlite` para la arquitectura de producción de `alo`:
1. **Compilación JIT en Wazero:** `ncruces/go-sqlite3` compila el código máquina Wasm a instrucciones de ensamblador de la CPU anfitriona en el primer uso. Las consultas sobre índices FTS5 y uniones temporales de Lebesgue se ejecutan a velocidades equivalentes a bibliotecas dinámicas de C.
2. **Cero Polución del Heap de Go:** Los cientos de miles de registros de telemetría y tickets cacheados no generan punteros dentro del grafo de escaneo del recolector de basura de Go, evitando latencias de micro-pausa en el bucle interactivo de la TUI.
3. **Fidelidad Bit a Bit de SQLite:** Al utilizar el Wasm generado directamente desde el árbol oficial del consorcio SQLite (`sqlite-amalgamation`), la semántica de bloqueos ACID, journals y recovery ante cortes de energía es idéntica a la del motor C de producción.

### 4.2 Arquitectura de Concurrencia: El Patrón Dual-Pool en Modo WAL

SQLite en modo WAL soporta múltiples lectores concurrentes pero **exactamente un único escritor a la vez**. Si el pool estándar de `database/sql` abre múltiples conexiones y varias goroutines intentan escribir simultáneamente, se desata el infame error `database is locked (5)`.

La arquitectura hexagonal de `alo` implementa el patrón **Dual Connection Pool**:

```text
                               ┌───────────────────────────┐
                               │     Storage Adapter       │
                               │        (SQLite)           │
                               └─────────────┬─────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
          [POOL DE ESCRITURA ATÓMICA]                   [POOL DE LECTURA CONCURRENTE]
        • MaxOpenConns: 1                             • MaxOpenConns: NumCPU * 2
        • MaxIdleConns: 1                             • MaxIdleConns: NumCPU
        • Exclusivo para INSERT/UPDATE/DELETE         • Exclusivo para SELECT / FTS5
        • PRAGMA busy_timeout = 10000ms               • PRAGMA query_only = ON
```

#### Código del Adaptador de Conexión SQLite Seguro:

```go
package sqlite

import (
	"context"
	"database/sql"
	"fmt"
	"runtime"
	"time"

	_ "github.com/ncruces/go-sqlite3/driver"
	_ "github.com/ncruces/go-sqlite3/embed"
)

type DB struct {
	writer *sql.DB
	reader *sql.DB
}

func Open(dsn string) (*DB, error) {
	// 1. Instanciar conexión de escritura única
	writer, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, fmt.Errorf("abriendo writer sqlite: %w", err)
	}
	writer.SetMaxOpenConns(1)
	writer.SetMaxIdleConns(1)
	writer.SetConnMaxLifetime(0)

	// Configurar PRAGMAs críticos de escritura
	writerPragmas := []string{
		"PRAGMA journal_mode = WAL;",
		"PRAGMA busy_timeout = 10000;",
		"PRAGMA synchronous = NORMAL;",
		"PRAGMA foreign_keys = ON;",
		"PRAGMA temp_store = MEMORY;",
	}
	for _, pragma := range writerPragmas {
		if _, err := writer.Exec(pragma); err != nil {
			_ = writer.Close()
			return nil, fmt.Errorf("configurando pragma writer '%s': %w", pragma, err)
		}
	}

	// 2. Instanciar pool de lectura concurrente
	reader, err := sql.Open("sqlite3", dsn)
	if err != nil {
		_ = writer.Close()
		return nil, fmt.Errorf("abriendo reader sqlite: %w", err)
	}
	maxReaders := runtime.NumCPU() * 2
	if maxReaders < 4 {
		maxReaders = 4
	}
	reader.SetMaxOpenConns(maxReaders)
	reader.SetMaxIdleConns(maxReaders)
	reader.SetConnMaxIdleTime(5 * time.Minute)

	readerPragmas := []string{
		"PRAGMA busy_timeout = 5000;",
		"PRAGMA foreign_keys = ON;",
		"PRAGMA query_only = ON;",
	}
	for _, pragma := range readerPragmas {
		if _, err := reader.Exec(pragma); err != nil {
			_ = writer.Close()
			_ = reader.Close()
			return nil, fmt.Errorf("configurando pragma reader '%s': %w", pragma, err)
		}
	}

	return &DB{writer: writer, reader: reader}, nil
}

func (db *DB) Reader() *sql.DB { return db.reader }
func (db *DB) Writer() *sql.DB { return db.writer }

func (db *DB) Close() error {
	errW := db.writer.Close()
	errR := db.reader.Close()
	if errW != nil {
		return errW
	}
	return errR
}
```

### 4.3 Migraciones de Esquema Deterministas sin ORMs Pesados

Prohibimos terminantemente el uso de GORM, Ent o frameworks de migración con estado dinámico. Se adopta el estándar de **migraciones SQL deterministas embebidas** mediante `embed.FS` de la biblioteca estándar de Go:

```text
internal/adapters/storage/sqlite/migrations/
├── 0001_initial_schema.sql
├── 0002_fts5_issues_search.sql
└── 0003_outbox_and_watermarks.sql
```

```go
package sqlite

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"embed"
	"fmt"
	"sort"
	"strings"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

type MigrationEngine struct {
	db *sql.DB // Debe ser la conexión de escritura única
}

func NewMigrationEngine(writerDB *sql.DB) *MigrationEngine {
	return &MigrationEngine{db: writerDB}
}

func (m *MigrationEngine) Migrate(ctx context.Context) error {
	tx, err := m.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return fmt.Errorf("iniciando transaccion de migracion: %w", err)
	}
	defer tx.Rollback()

	// Crear tabla de metadatos de migraciones si no existe
	_, err = tx.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version INTEGER PRIMARY KEY,
			name TEXT NOT NULL,
			applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			checksum TEXT NOT NULL
		);
	`)
	if err != nil {
		return fmt.Errorf("creando schema_migrations: %w", err)
	}

	entries, err := migrationFiles.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("leyendo migraciones embebidas: %w", err)
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})

	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}

		var version int
		var name string
		_, err := fmt.Sscanf(entry.Name(), "%d_%s", &version, &name)
		if err != nil {
			return fmt.Errorf("nombre de migracion invalido '%s': %w", entry.Name(), err)
		}

		// Comprobar si ya fue aplicada
		var count int
		err = tx.QueryRowContext(ctx, "SELECT COUNT(1) FROM schema_migrations WHERE version = ?", version).Scan(&count)
		if err != nil {
			return fmt.Errorf("verificando version %d: %w", version, err)
		}
		if count > 0 {
			continue // Ya aplicada
		}

		content, err := migrationFiles.ReadFile("migrations/" + entry.Name())
		if err != nil {
			return fmt.Errorf("leyendo archivo %s: %w", entry.Name(), err)
		}

		checksum := fmt.Sprintf("%x", sha256.Sum256(content))

		// Ejecutar script SQL de la migracion
		if _, err := tx.ExecContext(ctx, string(content)); err != nil {
			return fmt.Errorf("fallo al ejecutar migracion %s: %w", entry.Name(), err)
		}

		// Registrar migracion aplicada
		_, err = tx.ExecContext(ctx, `
			INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)
		`, version, entry.Name(), checksum)
		if err != nil {
			return fmt.Errorf("registrando migracion %d: %w", version, err)
		}
	}

	return tx.Commit()
}
```

---

## 5. Mecánica de Git y Worktrees Multi-Repo de Alta Resiliencia

El orquestador de espacios de trabajo (`Workspace Isolator`) debe interactuar con el binario `git` instalado en el sistema anfitrión. Sin embargo, dicha interacción debe estar blindada contra fallos de versión, cuelgues de red y brechas de inyección.

```text
                        ┌──────────────────────────────────────────┐
                        │      Git CLI Resilient Orchestrator      │
                        │        (internal/adapters/git/cli)       │
                        └────────────────────┬─────────────────────┘
                                             │
             ┌───────────────────────────────┼───────────────────────────────┐
             ▼                               ▼                               ▼
  [FEATURE DETECTION]              [ISOLATION & RESILIENCE]       [INJECTION DEFENSE]
• git --version parseo           • context.WithTimeout (15s)    • Flag injection guards:
• Soporte merge-tree write-tree  • Setpgid: true (POSIX)          - regex estricto de slug/rama
  (Git >= 2.38)                  • syscall.Kill(-pgid, SIGKILL)   - prohibir inicio con '-'
• Degrada si Git < 2.38            en cancelación de contexto   • Uso mandatorio de '--'
```

### 5.1 Matriz de Compatibilidad y Feature Detection en Arranque

```go
package gitcli

import (
	"context"
	"fmt"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

type GitCapabilities struct {
	RawVersion             string
	Major                  int
	Minor                  int
	Patch                  int
	SupportsMergeTreeWrite bool // Git >= 2.38
	SupportsWorktreeConfig bool // Git >= 2.30
}

var (
	capabilitiesCache *GitCapabilities
	capabilitiesOnce  sync.Once
)

func DetectCapabilities(ctx context.Context) (*GitCapabilities, error) {
	var detectErr error
	capabilitiesOnce.Do(func() {
		ctxTimeout, cancel := context.WithTimeout(ctx, 3*time.Second)
		defer cancel()

		cmd := exec.CommandContext(ctxTimeout, "git", "--version")
		out, err := cmd.Output()
		if err != nil {
			detectErr = fmt.Errorf("git no esta instalado o no responde en el PATH: %w", err)
			return
		}

		caps, err := parseGitVersion(string(out))
		if err != nil {
			detectErr = err
			return
		}
		capabilitiesCache = caps
	})

	return capabilitiesCache, detectErr
}

var gitVersionRegex = regexp.MustCompile(`git version (\d+)\.(\d+)(?:\.(\d+))?`)

func parseGitVersion(output string) (*GitCapabilities, error) {
	matches := gitVersionRegex.FindStringSubmatch(strings.TrimSpace(output))
	if len(matches) < 3 {
		return nil, fmt.Errorf("formato de version git ininteligible: '%s'", output)
	}

	major, _ := strconv.Atoi(matches[1])
	minor, _ := strconv.Atoi(matches[2])
	patch := 0
	if len(matches) >= 4 && matches[3] != "" {
		patch, _ = strconv.Atoi(matches[3])
	}

	caps := &GitCapabilities{
		RawVersion: output,
		Major:      major,
		Minor:      minor,
		Patch:      patch,
	}

	// Git >= 2.38 introdujo git merge-tree --write-tree
	if major > 2 || (major == 2 && minor >= 38) {
		caps.SupportsMergeTreeWrite = true
	}

	// Git >= 2.30 introdujo extensions.worktreeConfig estable
	if major > 2 || (major == 2 && minor >= 30) {
		caps.SupportsWorktreeConfig = true
	}

	return caps, nil
}
```

### 5.2 Prevención Rigurosa de Flag Injection y Ataques de Argumentos

No basta con no invocar `sh -c`. Si un desarrollador malicioso o un nombre de rama externo recibido de una API contiene `--upload-pack`, `git` puede ejecutar código arbitrario:

```go
package gitcli

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
)

var (
	ErrUnsafeIdentifier = errors.New("identificador de git no seguro")
	validBranchName     = regexp.MustCompile(`^[a-zA-Z0-9_\-\./]+$`)
	validTicketSlug     = regexp.MustCompile(`^[A-Za-z0-9]+-[0-9]+-[a-z0-9\-]+$`)
)

func SanitizeBranchName(name string) (string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return "", fmt.Errorf("%w: nombre de rama vacio", ErrUnsafeIdentifier)
	}
	if strings.HasPrefix(name, "-") {
		return "", fmt.Errorf("%w: el nombre de rama no puede comenzar con guion ('%s')", ErrUnsafeIdentifier, name)
	}
	if !validBranchName.MatchString(name) {
		return "", fmt.Errorf("%w: caracteres ilegales en rama '%s'", ErrUnsafeIdentifier, name)
	}
	return name, nil
}
```

### 5.3 Aislamiento de Procesos POSIX y Terminación de Zombies

Cuando se ejecutan operaciones con la red (ej. `git fetch`), se debe forzar que el comando cree un nuevo **Process Group** (`Setpgid: true`). Si expira el timeout, el signal `SIGKILL` debe enviarse a todo el grupo negativo `-pgid`:

```go
package gitcli

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"syscall"
	"time"
)

func (c *Client) runGitCommand(ctx context.Context, repoDir string, args ...string) ([]byte, error) {
	ctxTimeout, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctxTimeout, "git", args...)
	cmd.Dir = repoDir

	// Aislar en un process group propio en sistemas Unix/Linux
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Setpgid: true,
	}

	// Cancel handler para liquidar el grupo completo en caso de timeout
	cmd.Cancel = func() error {
		if cmd.Process != nil {
			pgid, err := syscall.Getpgid(cmd.Process.Pid)
			if err == nil {
				_ = syscall.Kill(-pgid, syscall.SIGKILL)
			}
		}
		return nil
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("fallo git %s en '%s': %w (stderr: %s)", args[0], repoDir, err, stderr.String())
	}

	return stdout.Bytes(), nil
}
```

---

## 6. Diseño de Arquitectura Hexagonal y SOLID Canónico en Go

La arquitectura de `alo` se erige sobre la separación formal de responsabilidades definida por Alistair Cockburn (Hexagonal) y Robert C. Martin (Clean Architecture), adaptada idiomáticamente a Go:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ARQUITECTURA HEXAGONAL DE ALOSTASIS                             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                  PRIMARY / DRIVING                                     │
│     ┌────────────────────────────────────────────────────────────────────────────┐     │
│     │                      ADAPTERS DE PRESENTACIÓN (UI)                         │     │
│     │  • JSONPresenter (Headless/IA)        • PlainTextPresenter (Pipes/CI)      │     │
│     │  • Bubble Tea TUI Model (Cockpit)     • Huh Wizard Forms (Humano)          │     │
│     └─────────────────────────────────────┬──────────────────────────────────────┘     │
│                                           │ llama a                                    │
│                                           ▼                                            │
│     ┌────────────────────────────────────────────────────────────────────────────┐     │
│     │                      INPUT PORTS (CASOS DE USO)                            │     │
│     │  • LedgerService (Agenda, Flow, Lebesgue) • SyncService (CQS Delta)        │     │
│     │  • WorkspaceService (Multi-Repo Git)      • OutboxService (Idempotencia)   │     │
│     └─────────────────────────────────────┬──────────────────────────────────────┘     │
│                                           │ orquesta                                   │
│                                           ▼                                            │
│     ┌────────────────────────────────────────────────────────────────────────────┐     │
│     │                       CORE DE DOMINIO INMUTABLE                            │     │
│     │  • Value Objects: TicketID, Interval, LebesgueMeasure, CapacityBucket      │     │
│     │  • Agregados: Worklog, Issue, WorktreeContainer, StateTimeline             │     │
│     │  • Invariantes & Reglas Puras: Little's Law, Klee Merge, Cycle Time        │     │
│     └─────────────────────────────────────┬──────────────────────────────────────┘     │
│                                           │ define contratos para                      │
│                                           ▼                                            │
│     ┌────────────────────────────────────────────────────────────────────────────┐     │
│     │                     OUTPUT PORTS (INTERFACES SALIENTES)                    │     │
│     │  • LedgerRepositoryPort               • IssueTrackerRemotePort             │     │
│     │  • GitWorkspacePort                   • ClockPort (Frozen/System)          │     │
│     └─────────────────────────────────────┬──────────────────────────────────────┘     │
│                                           │ implementado por                           │
│                                           ▼                                            │
│                                 SECONDARY / DRIVEN                                     │
│     ┌────────────────────────────────────────────────────────────────────────────┐     │
│     │                   ADAPTERS DE INFRAESTRUCTURA & I/O                        │     │
│     │  • storage/sqlite (ncruces, WAL)      • remote/plane (REST, CircuitBreak)  │     │
│     │  • git/cli (Resilient, POSIX group)   • clock/system (Real/Frozen Clock)   │     │
│     └────────────────────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Estructura Canónica de Paquetes en Go

```text
alo/
├── cmd/
│   └── alo/
│       └── main.go                 # Entrypoint Único, Flag Multiplexer, Composition Root
│
├── internal/
│   ├── domain/                     # 100% Go Standard Library (Zero dependencias externas)
│   │   ├── ledger/                 # Intervalos de Klee, Algoritmo Lebesgue, CapacityBucket
│   │   │   ├── interval.go
│   │   │   ├── lebesgue.go
│   │   │   └── worklog.go
│   │   ├── flow/                   # Métricas de Little's Law, WIP Watcher, Lead/Cycle Time
│   │   │   ├── metrics.go
│   │   │   └── timeline.go
│   │   ├── issue/                  # Ticket, Estado, Prioridad, Asignado, Watermark
│   │   │   ├── issue.go
│   │   │   └── state.go
│   │   ├── workspace/              # Contenedor Multi-Repo, Bindings, Estado de Merge
│   │   │   ├── container.go
│   │   │   └── merge_state.go
│   │   ├── clock/                  # Contrato de Reloj y tipos de tiempo inmutables
│   │   │   └── clock.go
│   │   └── errors.go               # Errores centinela del dominio (ErrTicketNotFound, etc.)
│   │
│   ├── ports/                      # Contratos e Interfaces de Entrada y Salida
│   │   ├── in/                     # Input Ports (Casos de uso llamados por UI/CLI)
│   │   │   ├── ledger_usecase.go
│   │   │   ├── sync_usecase.go
│   │   │   └── workspace_usecase.go
│   │   └── out/                    # Output Ports (Llamados por Casos de uso hacia afuera)
│   │       ├── repository.go       # LedgerRepositoryPort, IssueRepositoryPort
│   │       ├── tracker.go          # RemoteTrackerPort (Plane, Linear, GitHub)
│   │       ├── git.go              # GitWorkspacePort
│   │       └── presenter.go        # PresenterPort (JSON, PlainText, TUI)
│   │
│   ├── application/                # Implementación de Casos de Uso (Orquestación Pura)
│   │   ├── ledger_service.go       # LogSessionUseCase, QueryAgendaUseCase
│   │   ├── sync_service.go         # DeltaSyncUseCase, OutboxFlushUseCase
│   │   └── workspace_service.go    # CreateWorkspaceUseCase, AuditMergeUseCase
│   │
│   ├── adapters/                   # Implementaciones concretas de infraestructura
│   │   ├── storage/sqlite/         # Driver ncruces/go-sqlite3, pool WAL dual, FTS5
│   │   │   ├── client.go
│   │   │   ├── ledger_repo.go
│   │   │   ├── issue_repo.go
│   │   │   └── migrations/
│   │   ├── remote/plane/           # Cliente HTTP REST, Circuit Breaker, Exponential Backoff
│   │   │   ├── client.go
│   │   │   └── mapper.go
│   │   ├── git/cli/                # Wrapper tipado de Git con Feature Detection y pgid
│   │   │   ├── client.go
│   │   │   ├── worktree.go
│   │   │   └── merge_tree.go
│   │   ├── clock/                  # Implementaciones de Clock (SystemClock, FrozenClock)
│   │   │   └── clock.go
│   │   └── ui/                     # Adaptadores de presentación
│   │       ├── execution.go        # Detección determinista de TTY y modo
│   │       ├── json/               # Formateador JSON estructurado para Agentes IA
│   │       ├── plain/              # Formateador de texto plano para pipes/scripts
│   │       └── tui/                # Bucle interactivo Bubble Tea con Lipgloss y Huh
│   │           ├── root_model.go
│   │           ├── views/
│   │           └── styles/
│   │
│   └── bootstrap/                  # Inyección de Dependencias Manual y Composición
│       └── container.go            # Composition Root determinista
```

### 6.2 Agregados y Value Objects de Dominio (Ejemplo: Medida de Lebesgue)

El núcleo de dominio nunca importa `database/sql`, `net/http` ni paquetes de terceros:

```go
package ledger

import (
	"errors"
	"sort"
	"time"
)

var (
	ErrInvalidInterval = errors.New("el tiempo de fin debe ser estrictamente posterior al inicio")
	ErrDegenerateBlock = errors.New("intervalo con duracion cero o negativa")
)

// Interval es un Value Object inmutable que representa un tramo continuo de tiempo.
type Interval struct {
	start time.Time
	end   time.Time
}

func NewInterval(start, end time.Time) (Interval, error) {
	if !end.After(start) {
		return Interval{}, ErrInvalidInterval
	}
	return Interval{start: start, end: end}, nil
}

func (i Interval) Start() time.Time     { return i.start }
func (i Interval) End() time.Time       { return i.end }
func (i Interval) Duration() time.Duration { return i.end.Sub(i.start) }

// CalculateLebesgueMeasure calcula la medida unidimensional de Lebesgue (Klee)
// resolviendo de forma determinista cualquier solapamiento de intervalos.
func CalculateLebesgueMeasure(intervals []Interval) time.Duration {
	if len(intervals) == 0 {
		return 0
	}

	valid := make([]Interval, len(intervals))
	copy(valid, intervals)

	sort.Slice(valid, func(i, j int) bool {
		return valid[i].start.Before(valid[j].start)
	})

	var totalDuration time.Duration
	curStart := valid[0].start
	curEnd := valid[0].end

	for _, it := range valid[1:] {
		if !it.start.After(curEnd) {
			if it.end.After(curEnd) {
				curEnd = it.end
			}
		} else {
			totalDuration += curEnd.Sub(curStart)
			curStart = it.start
			curEnd = it.end
		}
	}
	totalDuration += curEnd.Sub(curStart)

	return totalDuration
}
```

### 6.3 Inversión de Dependencias sin Frameworks Mágicos (Clean Composition Root)

En herramientas CLI donde el tiempo de arranque debe ser <10ms, el uso de frameworks de inyección reflexiva (como Uber Dig o Fx) penaliza el tiempo de inicio e introduce errores en runtime.
Se utiliza el patrón **Manual Constructor Composition** en `internal/bootstrap/container.go`:

```go
package bootstrap

import (
	"context"
	"fmt"
	"path/filepath"

	"github.com/allostasis/alo/internal/adapters/clock"
	"github.com/allostasis/alo/internal/adapters/git/cli"
	"github.com/allostasis/alo/internal/adapters/remote/plane"
	"github.com/allostasis/alo/internal/adapters/storage/sqlite"
	"github.com/allostasis/alo/internal/application"
	"github.com/allostasis/alo/internal/domain/clock"
	"github.com/allostasis/alo/internal/ports/in"
)

type Container struct {
	LedgerService    in.LedgerUseCase
	SyncService      in.SyncUseCase
	WorkspaceService in.WorkspaceUseCase
	Clock            domainclock.Clock
	DB               *sqlite.DB
}

type Config struct {
	DataDir      string
	PlaneBaseURL string
	PlaneAPIKey  string
	IsDryRun     bool
}

func BuildContainer(ctx context.Context, cfg Config) (*Container, error) {
	// 1. Instanciar Clock
	sysClock := clock.NewSystemClock()

	// 2. Instanciar SQLite con Dual-Pool y ejecutar migraciones
	dbPath := filepath.Join(cfg.DataDir, "worklogs.db")
	db, err := sqlite.Open(dbPath)
	if err != nil {
		return nil, fmt.Errorf("iniciando base de datos: %w", err)
	}

	migrator := sqlite.NewMigrationEngine(db.Writer())
	if err := migrator.Migrate(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ejecutando migraciones: %w", err)
	}

	// 3. Instanciar Repositorios
	ledgerRepo := sqlite.NewLedgerRepository(db)
	issueRepo := sqlite.NewIssueRepository(db)

	// 4. Instanciar Adaptadores Externos
	planeClient := plane.NewClient(cfg.PlaneBaseURL, cfg.PlaneAPIKey)
	gitClient := gitcli.NewClient()

	// 5. Instanciar Casos de Uso (Application Services)
	ledgerSvc := application.NewLedgerService(ledgerRepo, sysClock)
	syncSvc := application.NewSyncService(issueRepo, planeClient, sysClock)
	wsSvc := application.NewWorkspaceService(gitClient, issueRepo, sysClock)

	return &Container{
		LedgerService:    ledgerSvc,
		SyncService:      syncSvc,
		WorkspaceService: wsSvc,
		Clock:            sysClock,
		DB:               db,
	}, nil
}
```

### 6.4 Manejo Idiomático de Errores con Jerarquía y Wrapping

Se define una jerarquía estricta de errores con valores centinela (`sentinel errors`) en el dominio, complementada con tipos estructurados para preservar causas y códigos de salida:

```go
package domain

import (
	"errors"
	"fmt"
)

// Errores Centinela de Dominio
var (
	ErrTicketNotFound      = errors.New("ticket no encontrado en el sistema")
	ErrTicketAlreadyClosed = errors.New("el ticket se encuentra cerrado o archivado")
	ErrWorkspaceDirty      = errors.New("el worktree contiene cambios no commiteados")
	ErrMergeConflict       = errors.New("conflicto no resoluble en merge en memoria")
	ErrRateLimitExceeded   = errors.New("tasa limite de peticiones superada en tracker remoto")
)

type ErrorCode string

const (
	CodeNotFound       ErrorCode = "NOT_FOUND"
	CodePrecondition   ErrorCode = "PRECONDITION_FAILED"
	CodeConflict       ErrorCode = "CONFLICT"
	CodeInfrastructure ErrorCode = "INFRASTRUCTURE_FAILURE"
)

type DomainError struct {
	Code    ErrorCode
	Message string
	Err     error
}

func (e *DomainError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("[%s] %s: %v", e.Code, e.Message, e.Err)
	}
	return fmt.Sprintf("[%s] %s", e.Code, e.Message)
}

func (e *DomainError) Unwrap() error {
	return e.Err
}

func WrapError(code ErrorCode, message string, cause error) error {
	return &DomainError{
		Code:    code,
		Message: message,
		Err:     cause,
	}
}
```

En la frontera de infraestructura, los adaptadores transforman errores del sistema operativo o SQLite en errores de dominio antes de propagarlos a la capa de aplicación:

```go
// En sqlite/issue_repo.go
func (r *IssueRepository) GetByID(ctx context.Context, id domain.TicketID) (*domain.Issue, error) {
	row := r.db.Reader().QueryRowContext(ctx, "SELECT id, title, state FROM issues_cache WHERE id = ?", id.String())
	var item domain.Issue
	if err := row.Scan(&item.ID, &item.Title, &item.State); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("%w: %s", domain.ErrTicketNotFound, id)
		}
		return nil, domain.WrapError(domain.CodeInfrastructure, "error leyendo cache sqlite", err)
	}
	return &item, nil
}
```

### 6.5 Aplicación Estricta de Principios SOLID y Desacoplamiento Modular

Para garantizar que la base de código de `alo` permanezca limpia, extensible y libre de acoplamientos espurios a medida que evoluciona hacia el ecosistema Open Source, se aplican de forma rigurosa los principios SOLID en cada paquete y frontera de abstracción.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MAPA DE PRINCIPIOS SOLID EN ALOSTASIS                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ SRP (Single Responsibility)                                                            │
│ • 3 Bounded Contexts independientes: Telemetry/Ledger, Work Items/Issues, Workspaces.  │
│ • Cero modelos de base de datos compartidos; agregados estancos y autónomos.           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ OCP (Open/Closed Principle) & DIP (Dependency Inversion)                               │
│ • Workspace Isolator diseñado como módulo autónomo pluggable.                          │
│ • Opera como subcomando integrado ('alo ws') O como binario standalone ('alo-ws').     │
│ • Depende de abstracciones mínimas (VCSWorkspacePort, IssueContextResolver).           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ ISP (Interface Segregation Principle)                                                  │
│ • Eliminación de contratos 'gordos' monolíticos; interfaces mínimas en el consumidor:  │
│   IssueReader, IssueWriter, WorklogPusher, WorkspaceAuditor, WorkspacePruner.          │
│ • WorkspaceService solo depende de IssueReader (nunca de mutaciones ni del outbox).    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 6.5.1 SRP (Single Responsibility Principle): Ortogonalidad de Bounded Contexts y Agregados

El dominio se particiona en **tres contextos delimitados (Bounded Contexts) estrictamente ortogonales**:

```text
┌──────────────────────────────┬──────────────────────────────┬──────────────────────────────┐
│ 1. COCKPIT & TELEMETRY       │ 2. WORK ITEMS & TRACKER      │ 3. WORKSPACE ISOLATION       │
│    (Contexto: Ledger)        │    (Contexto: Issue)         │    (Contexto: Workspace)     │
├──────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│ • Agregado: WorklogSession   │ • Agregado: IssueEntity      │ • Agregado: WorkspaceEnv     │
│ • Value Objects:             │ • Value Objects:             │ • Value Objects:             │
│   - Interval, LebesgueMeasure│   - TicketID, State, Priority│   - RepoBinding, TreeSHA     │
│   - CapacityBucket (DW, Toil)│   - Watermark, OutboxMessage │   - MergeAuditState          │
│ • Responsabilidad Única:     │ • Responsabilidad Única:     │ • Responsabilidad Única:     │
│   Contabilidad temporal pura,│   Caché CQS local, FTS5,     │   Aislamiento en disco,      │
│   Klee unions, balance de    │   sincronización delta y     │   creación atómica de ramas, │
│   esfuerzo sin tocar Git.    │   cola de salida idempotente.│   3-way merge audit in-memory│
└──────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

**Regla de Aislamiento Innegociable:**
- Ningún agregado de un contexto puede modificar o contener instancias vivas de agregados de otro contexto.
- Las referencias cruzadas se realizan únicamente mediante identificadores planos (`domain.TicketID`).
- No existen claves foráneas que fuercen acoplamiento transaccional entre las tablas de telemetría (`worklogs`), tickets (`issues_cache`) y worktrees en disco.

#### 6.5.2 ISP (Interface Segregation Principle): Contratos Mínimos Orientados al Consumidor

En Go, las interfaces no se declaran en el paquete proveedor (como en Java/C#), sino en el **paquete consumidor** (`ports/out`), conteniendo únicamente los métodos que dicho consumidor realmente necesita.

Se sustituye la interfaz monolítica previa (`IssueTrackerPort`) por contratos finamente segregados:

```go
package ports

import (
	"context"
	"time"

	"github.com/allostasis/alo/internal/domain/issue"
	"github.com/allostasis/alo/internal/domain/ledger"
	"github.com/allostasis/alo/internal/domain/workspace"
)

// --- Contratos Segregados para Issues ---

// IssueReader solo expone operaciones de consulta (usado por WorkspaceService y CLI list).
type IssueReader interface {
	GetIssue(ctx context.Context, id issue.TicketID) (*issue.Issue, error)
	ListIssues(ctx context.Context, filter issue.Filter) ([]*issue.Issue, error)
}

// IssueWriter solo expone persistencia y mutaciones de estado local.
type IssueWriter interface {
	SaveIssue(ctx context.Context, item *issue.Issue) error
	BatchUpsertIssues(ctx context.Context, items []*issue.Issue) error
}

// IssueRemoteSync expone la sincronización delta contra APIs externas (Plane, Linear, GitHub).
type IssueRemoteSync interface {
	FetchDelta(ctx context.Context, since time.Time) ([]*issue.Issue, error)
}

// --- Contratos Segregados para Ledger / Telemetría ---

// WorklogWriter almacena entradas de tiempo locales en SQLite.
type WorklogWriter interface {
	SaveWorklog(ctx context.Context, entry *ledger.Worklog) error
}

// WorklogReader consulta intervalos y trazas de tiempo para la agenda y reportes.
type WorklogReader interface {
	QueryIntervals(ctx context.Context, start, end time.Time) ([]ledger.Interval, error)
	ListWorklogs(ctx context.Context, filter ledger.QueryFilter) ([]*ledger.Worklog, error)
}

// WorklogPusher es consumido por OutboxService para despachar horas a APIs remotas.
type WorklogPusher interface {
	PushRemoteWorklog(ctx context.Context, entry *ledger.Worklog) error
}

// --- Contratos Segregados para Workspace Isolation ---

// WorkspaceCreator orquesta la creación transaccional multi-repo en disco.
type WorkspaceCreator interface {
	CreateWorkspace(ctx context.Context, req workspace.CreateRequest) (*workspace.WorkspaceEnv, error)
}

// WorkspaceAuditor analiza en memoria la integración de ramas (3-way merge tree).
type WorkspaceAuditor interface {
	AuditMerges(ctx context.Context, containerSlug string) (*workspace.AuditReport, error)
}

// WorkspacePruner elimina directorios de trabajo y realiza backups preventivos.
type WorkspacePruner interface {
	PruneWorkspace(ctx context.Context, containerSlug string, force bool) (*workspace.PruneResult, error)
}
```

##### Demostración de ISP: El Consumo de `WorkspaceService`
Observa cómo `WorkspaceService` **únicamente** depende de `IssueReader` y de su adaptador de Git. No tiene acceso ni acoplamiento a `IssueWriter`, ni a `WorklogPusher`, ni a la cola de salida (`Outbox`):

```go
package application

import (
	"context"
	"fmt"

	"github.com/allostasis/alo/internal/domain/issue"
	"github.com/allostasis/alo/internal/domain/workspace"
	"github.com/allostasis/alo/internal/ports"
)

type WorkspaceService struct {
	git        ports.VCSWorkspacePort
	issueQuery ports.IssueReader // ISP: Solo lectura, sin mutaciones
}

func NewWorkspaceService(git ports.VCSWorkspacePort, issueQuery ports.IssueReader) *WorkspaceService {
	return &WorkspaceService{
		git:        git,
		issueQuery: issueQuery,
	}
}

func (s *WorkspaceService) CanPruneSafely(ctx context.Context, ticketID issue.TicketID) (bool, error) {
	// Consulta el estado del ticket usando el contrato segregado
	ticket, err := s.issueQuery.GetIssue(ctx, ticketID)
	if err != nil {
		return false, fmt.Errorf("verificando estado del ticket: %w", err)
	}

	// Invariante de negocio: solo seguro podar si está cerrado o completado
	return ticket.IsCompleted(), nil
}
```

#### 6.5.3 OCP (Open/Closed Principle) y DIP (Dependency Inversion): Desacoplamiento Dual de Worktrees

Un requisito estratégico es que la capacidad de orquestación de worktrees (ex `plane-worktree`) pueda:
1. Funcionar como un **subcomando de primer nivel** en el CLI integrado de Alostasis (`alo ws` / `alo workspace`).
2. Funcionar o distribuirse como una **herramienta CLI independiente** (`cmd/alo-ws/main.go` -> binario binario `alo-ws`), útil para usuarios o entornos que solo desean aislamiento multi-repo sin telemetría ni tracking de issues.
3. Extenderse a nuevos motores de control de versiones (ej. soporte futuro para Sapling o Jujutsu) **sin modificar una sola línea de código del dominio o de los casos de uso**.

```text
                               ┌───────────────────────────┐
                               │  VCSWorkspacePort (DIP)   │
                               │  (Contrato Abierto / OCP) │
                               └─────────────┬─────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
          [ADAPTADOR PRINCIPAL]                         [ADAPTADORES EXTENSIBLES]
        • GitCLIAdapter (os/exec)                     • SaplingAdapter (Futuro)
        • Feature Detection Git >= 2.38               • JujutsuAdapter (Futuro)
        • POSIX pgid isolation                        • InMemoryVCSMock (Tests unitarios)
```

##### Patrón de Módulos de Comandos Pluggables (`CommandModule`):

```go
package cli

import (
	"github.com/spf13/cobra"
)

// ServiceResolver abstrae el contenedor de inyección para desacoplar comandos.
type ServiceResolver interface {
	ResolveWorkspaceService() (ports.WorkspaceCreator, ports.WorkspaceAuditor, ports.WorkspacePruner)
}

// CommandModule define el contrato para subherramientas extensibles.
type CommandModule interface {
	Name() string
	Register(rootCmd *cobra.Command, resolver ServiceResolver)
}
```

##### Implementación del Módulo Workspace (`internal/adapters/ui/cli/workspace_module.go`):

```go
package cli

import (
	"github.com/spf13/cobra"
)

type WorkspaceModule struct{}

func NewWorkspaceModule() *WorkspaceModule {
	return &WorkspaceModule{}
}

func (m *WorkspaceModule) Name() string { return "workspace" }

func (m *WorkspaceModule) Register(parent *cobra.Command, resolver ServiceResolver) {
	wsCmd := &cobra.Command{
		Use:     "workspace",
		Aliases: []string{"ws"},
		Short:   "Orquestador transaccional de Git worktrees multi-repositorio",
	}

	creator, auditor, pruner := resolver.ResolveWorkspaceService()

	wsCmd.AddCommand(newAddCmd(creator))
	wsCmd.AddCommand(newAuditCmd(auditor))
	wsCmd.AddCommand(newPruneCmd(pruner))

	parent.AddCommand(wsCmd)
}
```

##### Composición 1: CLI Unificado Principal (`cmd/alo/main.go`):
```go
func main() {
    rootCmd := &cobra.Command{Use: "alo"}
    container := bootstrap.MustBuildContainer()

    // Registrar módulos integrados
    modules := []cli.CommandModule{
        cli.NewLedgerModule(),
        cli.NewIssueModule(),
        cli.NewWorkspaceModule(), // Integrado como 'alo ws'
    }
    for _, mod := range modules {
        mod.Register(rootCmd, container)
    }

    _ = rootCmd.Execute()
}
```

##### Composición 2: CLI Independiente Standalone (`cmd/alo-ws/main.go`):
En esta configuración, el binario `alo-ws` compila **exclusivamente** el orquestador de worktrees, inyectando un `NullIssueResolver` (DIP) si el usuario no tiene configurado un tracker de tareas:

```go
package main

import (
	"context"
	"os"

	"github.com/spf13/cobra"
	"github.com/allostasis/alo/internal/adapters/git/cli"
	"github.com/allostasis/alo/internal/adapters/ui/cli"
	"github.com/allostasis/alo/internal/application"
	"github.com/allostasis/alo/internal/domain/issue"
)

// StandaloneResolver satisface ServiceResolver sin cargar SQLite ni Plane.
type StandaloneResolver struct {
	wsService *application.WorkspaceService
}

func (s *StandaloneResolver) ResolveWorkspaceService() (ports.WorkspaceCreator, ports.WorkspaceAuditor, ports.WorkspacePruner) {
	return s.wsService, s.wsService, s.wsService
}

// NullIssueResolver implementa IssueReader degradando limpiamente (DIP).
type NullIssueResolver struct{}

func (NullIssueResolver) GetIssue(_ context.Context, id issue.TicketID) (*issue.Issue, error) {
	return issue.NewUnknownIssue(id), nil
}
func (NullIssueResolver) ListIssues(_ context.Context, _ issue.Filter) ([]*issue.Issue, error) {
	return nil, nil
}

func main() {
	rootCmd := &cobra.Command{
		Use:   "alo-ws",
		Short: "Sovereign Multi-Repo Git Worktree Isolator (Standalone Edition)",
	}

	gitAdapter := gitcli.NewClient()
	nullReader := NullIssueResolver{}
	wsService := application.NewWorkspaceService(gitAdapter, nullReader)

	resolver := &StandaloneResolver{wsService: wsService}
	module := cli.NewWorkspaceModule()
	module.Register(rootCmd, resolver)

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}
```

De este modo:
- El núcleo de negocio de Worktrees permanece 100% cerrado a modificaciones (OCP).
- Se abre a extensiones como binario embebido, plugin o binario independiente con cero dependencias externas.
- Depende de contratos abstractos (`VCSWorkspacePort`, `IssueReader`), nunca de implementaciones concretas (DIP).

---

## 7. Plan de Validación y Shadow Testing

Para asegurar una transición con **riesgo cero de regresión funcional**, se establece un protocolo de **Shadow Testing (Pruebas Espejo)** durante las fases de migración:

```text
                               ┌───────────────────────────┐
                               │  Test Harness de Control  │
                               │  (Golden Dataset 100+ DB) │
                               └─────────────┬─────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
          [LEGACY PYTHON RUNTIME]                        [NUEVO ALOSTASIS GO]
        • plane-tracker report time                    • alo report time --json
        • plane-worktree audit                         • alo ws audit --json
                      │                                             │
                      └──────────────────────┬──────────────────────┘
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │     Verificador de Diff   │
                               │  • JSON AST Canonical Eq. │
                               │  • Desvío temporal < 0.0s │
                               │  • Bitácoras idénticas    │
                               └───────────────────────────┘
```

1. **Equivalencia de Intervalos de Lebesgue:** Se someterán ambos motores a 10,000 trazas sintéticas aleatorias con solapamientos de 2 a 50 intervalos y saltos de medianoche. El desvío admisible en el cálculo de minutos totales es de **0.000000 minutos**.
2. **Determinismo de 3-Way Merge:** Se clonarán 50 casos de prueba de branches fusionadas vía Squash en GitHub. Tanto el script Python original como el cliente Go `gitcli` deben producir diagnósticos de equivalencia de árbol (`MERGE_TREE == BASE_TREE`) con 100% de coincidencia.
3. **Validación de Cero-ANSI en Agentes:** Una suite automatizada ejecutará `alo [subcomando] --json` redirigiendo la salida a un validador de bytes. Si la salida contiene el byte `0x1B` (escape) en cualquier posición, el pipeline de CI fallará de inmediato.

---

## 8. Conclusiones y Dictamen de Aprobación

La migración a Go bajo la arquitectura y directrices técnicas aquí expuestas proporciona:

1. **Seguridad Operativa para Agentes de IA:** A través del desacoplamiento formal con `PresenterPort` y el cortafuegos de TTY, garantizando JSON prístino sin interferencias de secuencias ANSI ni bloqueos de terminal.
2. **Solidez de Almacenamiento Local-First:** Mediante `ncruces/go-sqlite3` con JIT en Wazero y el patrón de Dual Connection Pool en modo WAL, logrando concurrencia de lectura real sin bloqueos de contención ni penalización de GC.
3. **Resiliencia en Git Multi-Repo:** Mediante Feature Detection dinámico en el arranque, timeouts con control de grupos de procesos contra zombies y sanitización de argumentos contra inyecciones de flags.
4. **Mantenibilidad de Código Limpio:** Mediante una Arquitectura Hexagonal canónica en Go con inyección manual explícita, agregados inmutables y gestión idiomática de errores con `errors.Is` y `%w`.

Se autoriza el inicio inmediato de la construcción de **Alostasis (`alo`)** tomando esta especificación como el contrato arquitectónico supremo e inmutable del proyecto.