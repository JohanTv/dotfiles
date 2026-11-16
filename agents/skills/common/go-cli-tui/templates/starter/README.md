# {{ .AppTitle }}

{{ .Description }}

Estructura generada con la plantilla canónica **Go CLI/TUI + Arquitectura Hexagonal**.

## Características
- **Dualidad Innegociable:** Modo M2M estructurado (`--json` con `ResponseEnvelope` y códigos POSIX) y modo interactivo humano con Charm TUI (`bubbletea`).
- **Persistencia Soberana Pure-Go:** SQLite embebido con `ncruces/go-sqlite3` (Wazero JIT), `CGO_ENABLED=0`, modo WAL y aislamiento Dual-Pool.
- **Motor Documental Integrado:** Generador y linter de documentación técnica en Go (`cmd/docgen`) con validación de enlaces relativos y prevención de desincronización en CI (`make docs-check`).

## Comandos Rápidos
```bash
make build       # Compila bin/{{ .AppName }}
make test        # Ejecuta tests unitarios con -race
make docs        # Regenera docs/INDEX.md
make docs-check  # Linter de documentación y enlaces en CI
make install     # Instala en ~/.local/bin/{{ .AppName }}
```

## Para Agentes de IA y Contribuidores
Consulte [`AGENTS.md`](AGENTS.md) para las directrices de arquitectura, invariantes inquebrantables de código y el checklist de verificación antes de cada commit.
