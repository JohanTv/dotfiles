# Backlog de Producto y Deuda Técnica

Este documento es el registro de fricción cero para anotar ideas diferidas, defectos conocidos o refactors pendientes sin requerir metadatos YAML.

---

### Defectos Conocidos (Bugs)
- *(Ningún defecto activo conocido)*

---

### Mejoras Diferidas (Enhancements)
- Soporte para exportación en formato YAML en CLI (`--yaml`).
- Tema visual configurable en la TUI vía archivo de configuración.

---

### Funcionalidades Recientemente Implementadas
- [x] Protocolo dual `--json` con `ResponseEnvelope` ([RFC 0002](rfcs/0002-canonical-cli-contract.md)).
- [x] Persistencia SQLite Pure-Go con WAL ([ADR 0001](decisions/0001-initial-architecture.md)).
