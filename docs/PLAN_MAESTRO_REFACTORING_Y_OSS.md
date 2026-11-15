# Plan Maestro: Saneamiento de Dotfiles, Arquitectura Hexagonal y Génesis de Allostasis (OSS)

> **Estado:** Especificación de Arquitectura de Referencia / Aprobada  
> **Nombre del Producto:** Allostasis (alias CLI: `alo`)  
> **Tagline:** *"The Sovereign Developer Cockpit for Flow, Invisible Work, and Cognitive Load Regulation"*  
> **Fecha:** Noviembre 2026  
> **Autores:** Johan & AI Architecture Board  

---

## 1. Visión Ejecutiva y Diagnóstico

### 1.1 El Problema Actual (Monolito Acoplado en Dotfiles)
El repositorio de `dotfiles` actualmente sufre de un problema de **cohesión rota y acoplamiento estructural**:
1. **Mezcla de responsabilidades:** Contiene simultáneamente configuraciones de entorno (`.zshrc`, `alacritty.toml`, `config.kdl`) y aplicaciones de software empresarial completas (`plane-tracker` y `plane-worktree`) con bases de datos SQLite, 50+ suites de tests de Python y decenas de RFCs.
2. **Contaminación del historial Git:** Más del 85% de los commits históricos de dotfiles son desarrollo de features y correcciones del CLI de Plane, ocultando la trazabilidad del entorno de trabajo.
3. **Prompt Stuffing y asimetría de Skills:** Reglas globales (`active-rules.md`) inyectaban sintaxis y flags de Plane en cada turno de conversación, mientras que herramientas como Claude Code u OpenCode operaban a ciegas sin un catálogo estandarizado de skills bajo demanda.

### 1.2 La Solución de Arquitectura
1. **Saneamiento de `dotfiles`:** Rediseño modular de reglas (`core.md`, `skills-index.md`, `work.md`), implementando jerarquía obligatoria de edición nativa, prohibición terminante de `sed`, y catálogo de divulgación progresiva (*Progressive Disclosure*).
2. **Extracción Soberana (Nuevo Repositorio OSS):** Extracción de `plane-tracker` y `plane-worktree` hacia un nuevo repositorio de código abierto en `~/Code/allostasis`, conservando el 100% del historial de Git (191+ commits).
3. **Fusión en un Ecosistema Unificado:** Integración de la telemetría del desarrollador y la orquestación de Git worktrees bajo un mismo producto con Arquitectura Hexagonal y Bounded Contexts en Go con el ecosistema Charm.

---

## 2. Naming e Identidad del Producto Open Source

### Nombre Principal: **`ALLOSTASIS`** (Alias CLI: **`alo`**)

> *"Allostasis: The Sovereign Developer Cockpit for Flow, Invisible Work, and Cognitive Load Regulation."*

#### Fundamento Ontológico (Biología, Medicina y Teoría de Sistemas):
- **Alostasis vs Homeostasis:** Mientras que la homeostasis busca un equilibrio estático fijo, la **alostasis** es el proceso de alcanzar la estabilidad a través del cambio adaptativo continuo (*stability through change*).
- **Carga Alostática (*Allostatic Load*):** Es el desgaste acumulado por sobrecarga de interrupciones, soporte ad-hoc imprevisto, reuniones y *toil* invisible. El sistema mide esta carga, la hace visible y protege al desarrollador del agotamiento (*burnout*) mediante la Ley de Little (control de WIP) y el reloj inmutable.
- **Autonomía Endógena:** La regulación alostática es un proceso interno y soberano del organismo. Rechaza el software de vigilancia externa o *bossware*; el ledger es local en SQLite y las publicaciones upstream son proyecciones explícitas controladas por el ingeniero.

---

## 3. Plan de Implementación Holístico (5 Fases Ordenadas)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ FASE 0: Saneamiento y Endurecimiento de Dotfiles (Inmediato)               │
│ • core.md: Prohibición estricta de `sed`, jerarquía obligatoria de edición  │
│ • skills-index.md: Catálogo de Progressive Disclosure (Claude, Gemini, etc.)│
│ • work.md: Poda de comandos duplicados de Plane, delimitación determinista  │
│ • Makefile: Recompilación con active-rules.md y verificación doctor         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ FASE 1: Extracción Soberana y Skill de Arquitectura                        │
│ • Extracción con git-filter-repo preservando 191+ commits hacia ~/Code/alo  │
│ • Limpieza de dotfiles: eliminar código monolítico y enlazar vía symlink    │
│ • Creación de la Skill permanente go-cli-tui en dotfiles                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ FASE 2: Núcleo de Dominio y Entorno de Pruebas en Go                        │
│ • Setup de estructura estándar de carpetas Go (cmd/, internal/...)          │
│ • Dominio puro: Reloj determinista, Algoritmo de Klee, Ley de Little        │
│ • Table-Driven Tests y Golden Files al 100% de cobertura de lógica          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ FASE 3: Adaptadores de Infraestructura y Dual-Mode                          │
│ • ncruces/go-sqlite3 (Wazero pure-Go, WAL mode, FTS5 unicode61, dual-pool)  │
│ • Git CLI wrapper (os/exec, PGID isolation, feature detection Git 2.38+)    │
│ • Dual-Mode: Presentation Strategy (Headless JSON para IA vs TUI humana)    │
│ • Desacoplamiento de Worktrees (subcomando `alo ws` y standalone `alo-ws`)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ FASE 4: Experiencia TUI con Charm y Lanzamiento OSS                         │
│ • Implementación de TUI con Bubble Tea, Lip Gloss, Bubbles y Huh            │
│ • Packaging con GoReleaser (binarios estáticos para Linux/macOS/Windows)    │
│ • Publicación en GitHub con README y los activos visuales diseñados         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estructura Canónica de Carpetas (Standard Go Project Layout)

```text
allostasis/
├── cmd/
│   ├── alo/
│   │   └── main.go                 # Punto de entrada principal (CLI unificado)
│   └── alo-ws/
│       └── main.go                 # Subherramienta standalone de worktrees (opcional)
│
├── internal/
│   ├── bootstrap/
│   │   └── container.go            # Composition Root (inyección manual, cero reflexión)
│   │
│   ├── domain/                     # 🧠 Núcleo puro (cero dependencias de I/O)
│   │   ├── clock/                  # Reloj inmutable (Clock, RealClock, FrozenClock)
│   │   ├── telemetry/              # KleeInterval, Session, AllostaticLoad, Little's Law
│   │   ├── issues/                 # WorkItem, State, Comment, OutboxEvent
│   │   └── workspace/              # Container, WorktreeBranch, MergeStatus
│   │
│   ├── ports/                      # 🔌 Interfaces segregadas (ISP)
│   │   ├── in/                     # Casos de uso de entrada
│   │   │   ├── telemetry.go        # LogSessionUseCase, GetAgendaUseCase
│   │   │   └── workspace.go        # AddWorkspaceUseCase, AuditWorkspaceUseCase
│   │   └── out/                    # Puertos de salida
│   │       ├── repository.go       # WorklogReader, WorklogWriter, OutboxPusher
│   │       ├── tracker.go          # IssueReader, IssueSynchronizer
│   │       └── git.go              # GitWorkspaceExecutor, MergeAuditor
│   │
│   ├── adapters/                   # ⚙️ Implementaciones concretas de infraestructura
│   │   ├── sqlite/                 # ncruces/go-sqlite3 con Wazero, dual-pool WAL
│   │   │   ├── migrations/         # //go:embed *.sql (migraciones deterministas)
│   │   │   └── store.go
│   │   ├── gitcli/                 # os/exec con PGID isolation y feature detection
│   │   ├── tracker_plane/          # Cliente REST de Plane con Circuit Breaker
│   │   └── tracker_local/          # Almacenamiento local 100% offline
│   │
│   ├── presentation/               # 🖥️ Estrategias de salida (Dual-Mode)
│   │   ├── presenter.go            # Interface PresenterStrategy
│   │   ├── json/                   # Presenter JSON estructurado estricto para Agentes de IA
│   │   ├── plain/                  # Presenter para tuberías Unix
│   │   └── tui/                    # 🌸 Ecosistema Charm (The Elm Architecture)
│   │       ├── app.go              # Modelo raíz de Bubble Tea
│   │       ├── styles.go           # Lip Gloss (paleta cian, ámbar, dark abyss)
│   │       ├── views/              # Vistas: Agenda, WorktreeSelector, Formulario Huh
│   │       └── components/         # Tablas Bubbles, viewports y spinners
│   │
│   └── testutil/                   # 🧪 Harness y fakes de pruebas compartidos
│       ├── fakes.go                # Fakes en memoria de puertos (cero mocks frágiles)
│       └── git_sandbox.go          # Creador de repositorios Git efímeros en disco
│
├── testdata/                       # 📂 Archivos dorados de prueba
│   └── golden/                     # JSONs y salidas de texto esperadas
├── go.mod
├── go.sum
├── Makefile
├── LICENSE                         # Apache-2.0
└── README.md
```

---

## 5. Arquitectura Hexagonal y Contextos Delimitados (DDD)

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  ALLOSTASIS ECOSYSTEM                                  │
├──────────────────────────────┬──────────────────────────┬──────────────────────────────┤
│ 1. COCKPIT & TELEMETRY       │ 2. WORK ITEMS & TRACKER  │ 3. WORKSPACE ISOLATION       │
│    (Engineer's Ledger)       │    (Issue & State Engine)│    (Multi-Repo Orchestrator) │
├──────────────────────────────┼──────────────────────────┼──────────────────────────────┤
│ • Session Clock (Frozen)     │ • Work Items (Tickets)   │ • Transactional Pre-flight   │
│ • Worklogs (Klee Intervals)  │ • Outbox Idempotente     │ • Multi-repo Worktree Bind   │
│ • WIP Watcher (Little's Law) │ • Delta-Sync Engine      │ • 3-Way Merge Audit (Tree)   │
│ • Capacity Allocation        │ • Ports & Adapters:      │ • Safe Pruning & Tarball     │
│ • Standby Blocker Telemetry  │   [Plane|Linear|GH|Local]│ • Branch Hygiene & Slugs     │
└──────────────────────────────┴──────────────────────────┴──────────────────────────────┘
```

---

## 6. Entorno de Pruebas y Buenas Prácticas (Testing Harness)

1. **Table-Driven Tests:** Tests parametrizados en Go para Klee Measure, Little's Law y transiciones de estado.
2. **SQLite Efímero en Memoria (`file:alo_shared_mem?mode=memory&cache=shared`):** Pruebas de integración de base de datos en <20ms con `SetMaxOpenConns(1)` sin residuo en disco.
3. **Sandboxes Git Aislados (`t.TempDir()`):** Repositorios temporales para pruebas de worktree y `git merge-tree`.
4. **Golden File Testing:** Verificación estricta de salidas `--json` para que las refactorizaciones nunca rompan a agentes de IA (Claude Code / Gemini).
5. **Headless TUI Testing (`teatest`):** Simulación de pulsaciones de teclas en Bubble Tea de forma desatendida.

---

## 7. Protocolo de Errores para Agentes Autónomos de IA (Error Envelopes)

Para evitar la pérdida de contexto y tracebacks crípticos que rompían la inferencia de agentes en herramientas tradicionales:
- **Salida Estructurada Canónica (`ResponseEnvelope`):** Todo comando con `--json` emite un envelope determinista:
  ```json
  {
    "ok": false,
    "error": {
      "code": "INVALID_ARGUMENT",
      "message": "Duración de intervalo inválida: debe ser entero positivo",
      "hint": "Usa 'alo log <TICKET> <MINUTOS>' con minutos enteros",
      "recoverable": true
    }
  }
  ```
- **Sin Secuencias ANSI en Flujo JSON:** Se garantiza que `stderr` y `stdout` bajo `--json` no contengan códigos de color o cursor VT100 que rompan `json.Unmarshal`.
- **Accionabilidad Automática:** El campo `hint` le proporciona al agente la sugerencia directa de autoreparación sin necesidad de inferir la solución por ensayo y error.
