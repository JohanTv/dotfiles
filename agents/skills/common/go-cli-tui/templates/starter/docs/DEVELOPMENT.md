# Guía de Desarrollo e Ingeniería Interna: {{ .AppTitle }} (`{{ .AppName }}`)

> **Audiencia:** Ingenieros de Core y Agentes Autónomos de IA modificando, extendiendo o auditando el código fuente de `{{ .AppName }}`.  
> Si tu propósito es únicamente inducción operativa rápida o reglas de oro de ejecución, consulta [`AGENTS.md`](../AGENTS.md).

---

## 1. Contexto, Propósito y Arquitectura

**{{ .AppTitle }} (`{{ .AppName }}`)**: {{ .Description }}.

El proyecto está diseñado bajo la filosofía canónica de **Go CLI/TUI + Arquitectura Hexagonal**, concebido tanto para interacción humana en terminal como para orquestación sin fricción por agentes de IA:

### Stack y Decisiones Clave:
- **Arquitectura Hexagonal Pura (Ports & Adapters):** Dominio desacoplado en el centro. Interfaces de entrada en `internal/ports/in/` y de salida en `internal/ports/out/`. Adaptadores en `internal/adapters/`.
- **Pure-Go CGO_ENABLED=0:** Compilación 100% estática sin dependencias de toolchains de C ni enlaces dinámicos del sistema.
- **SQLite Embebido sobre WebAssembly (Wazero JIT):** Persistencia soberana Local-First vía `ncruces/go-sqlite3`.
- **Dual-Pool WAL Concurrency:** 1 escritor serializado (`SetMaxOpenConns(1)`) en modo WAL para prevenir `SQLITE_BUSY`, y un pool de lectores concurrentes escalado por CPU con `PRAGMA query_only=ON`.
- **Dualidad Innegociable M2M / Humana:**
  - **Headless M2M (`--json`):** Salida estructurada formal, determinista, libre de secuencias ANSI y con silenciamiento absoluto de `stderr`.
  - **TUI Reactiva Humana:** Interfaz interactiva basada en el ecosistema Charm ([Bubble Tea](https://github.com/charmbracelet/bubbletea), [Lip Gloss](https://github.com/charmbracelet/lipgloss)).

Para especificaciones canónicas de diseño, consulta [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) y [`docs/BACKLOG.md`](BACKLOG.md).

---

## 2. Comandos de Ciclo de Vida (`Makefile`)

Todo agente o colaborador que desarrolle o modifique código en este repositorio debe interactuar mediante los objetivos estándar del `Makefile`:

```bash
make build       # Compila el binario bin/{{ .AppName }} con CGO_ENABLED=0 y flags de versión
make test        # Ejecuta la suite de pruebas completa con race detector (-race)
make docs        # Regenera docs/INDEX.md a partir de los metadatos de RFCs y ADRs
make docs-check  # Linter de documentación en CI: valida enlaces relativos y consistencia
make install     # Compila e instala el binario en ~/.local/bin/{{ .AppName }}
make clean       # Elimina artefactos y binarios en bin/
```

> [!IMPORTANT]
> **Prohibición de bypass:** NUNCA compiles omitiendo `CGO_ENABLED=0`. NUNCA ejecutes pruebas unitarias omitiendo el flag `-race` (`go test -race ./...`).

---

## 3. Invariantes Profundos de Implementación

Al agregar funcionalidad o refactorizar código en `{{ .AppName }}`, debes cumplir estrictamente con los siguientes invariantes:

### 3.1. Núcleo de Dominio (`internal/domain/`)
- **Aislamiento Absoluto:** **Cero dependencias** hacia SQL, HTTP, Cobra, Bubble Tea o I/O de disco. Solo biblioteca estándar de Go (`time`, `math`, `sync`, `sort`, `errors`).
- **Independencia Tecnológica:** Las entidades y reglas de negocio del dominio nunca deben importar paquetes de `internal/adapters/`, `internal/presentation/` o `internal/ports/`.

### 3.2. Puertos Canónicos y Servicios (`internal/ports/`, `internal/bootstrap/`)
- **Segregación de Interfaces (ISP):**
  - Puertos de Entrada (`internal/ports/in/`): Métodos expuestos para la aplicación y presentación.
  - Puertos de Salida (`internal/ports/out/`): Métodos requeridos para persistencia e infraestructura externa.
- **Inversión de Dependencias (DIP):** Los servicios de aplicación implementan puertos de entrada y consumen puertos de salida. El composition root (`internal/bootstrap/container.go`) realiza el cableado de dependencias.
- **Zero Adapter Leaks:** Queda terminantemente prohibido que un adaptador dependa directamente de otro adaptador.

### 3.3. Presentación y Blindaje Machine-to-Machine (`internal/presentation/errors/`)
- **Silencio Absoluto en `stderr` bajo `--json`:** Si se pasa `--json`, `stderr` debe permanecer en **0 bytes**. Ningún log, texto plano o traza de error puede emitirse por `stderr`.
- **ResponseEnvelope Canónico:** Toda respuesta en modo M2M debe emitirse exclusivamente por `stdout` serializada en JSON conforme al contrato normativo:
  ```json
  {
    "ok": false,
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "category": "not_found",
      "message": "el recurso solicitado no existe",
      "hint": "Verifica los identificadores con '{{ .AppName }} list'",
      "recoverable": true
    }
  }
  ```
- **Códigos de Salida POSIX Estándar:**
  - `0`: Éxito.
  - `1`: Error interno o fallo de lógica.
  - `2`: Uso incorrecto del CLI / flag inválido (`UsageError`).
  - `3`: Recurso no encontrado.
  - `4`: Conflicto de estado o regla de negocio violada.

### 3.4. Terminal Firewall (`internal/presentation/tui/`)
- Si el proceso se ejecuta de forma no interactiva (tuberías, CI, agente) o con el flag `--json`, los componentes de Charm TUI **nunca** deben inicializarse ni intentar leer de `stdin`.

### 3.5. Adaptador de Persistencia SQLite (`internal/adapters/storage/sqlite/`)
- **Dual-Pool WAL:**
  - 1 conexión única de escritura (`SetMaxOpenConns(1)`) en modo WAL para eliminar bloqueos de concurrencia.
  - Múltiples conexiones de lectura concurrentes (`_pragma=query_only(ON)`).
- Esquema de base de datos declarativo y reproducible en `schema.sql`.

---

## 4. Ciclo de Vida Documental (`docs/`)

El repositorio mantiene su arquitectura y especificaciones sincronizadas mediante el motor documental en Go ([`cmd/docgen`](../cmd/docgen/main.go)).

### 4.1. Anotación Rápida de Bugs y Pendientes (`docs/BACKLOG.md`)
- Si identificas defectos, límites conocidos o mejoras técnicas diferidas:
  - Anótalos directamente en [`docs/BACKLOG.md`](BACKLOG.md) bajo `## 1. Known Defects` o `## 2. Deferred Enhancements`.
  - **Fricción cero:** No requiere frontmatter YAML ni IDs formales para notas operativas rápidas.
  - Al completar un ítem, muévelo a `## 3. Recently Implemented`.

### 4.2. Propuesta de Cambios y Contratos (`cmd/docgen`)
- Para nuevas propuestas arquitectónicas (ADRs) o contratos de interfaz (RFCs):
  ```bash
  # Crear un Architecture Decision Record
  go run ./cmd/docgen --new decision <slug-kebab-case> --title "Título de la decisión"

  # Crear una Request for Comments
  go run ./cmd/docgen --new rfc <slug-kebab-case> --title "Título de la propuesta"
  ```
- Tras redactar el archivo generado, sincroniza el índice maestro:
  ```bash
  make docs
  ```

### 4.3. Inmutabilidad Histórica
- **NUNCA borres un ADR o RFC** ya implementado o evaluado. Si una decisión es superada, cambia su frontmatter a `status: superseded` y actualiza con `make docs`.

---

## 5. Checklist de Verificación antes de Finalizar un Turno

Antes de dar por concluida cualquier intervención técnica en este repositorio, verifica:

1. [ ] **`make test`**: La suite de pruebas pasa limpia con `-race` (cero data races).
2. [ ] **`make docs-check`**: Documentación sincronizada, sin enlaces rotos ni discrepancias de IDs.
3. [ ] **`make build`**: El binario compila limpiamente en `bin/{{ .AppName }}` con `CGO_ENABLED=0`.
4. [ ] **`git status -s`**: Sin archivos temporales ni modificaciones imprevistas en el working tree.
