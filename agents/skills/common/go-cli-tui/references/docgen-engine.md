# Motor Documental Soberano (`cmd/docgen`): Especificación y Gobernanza

Este documento describe la arquitectura del generador y linter documental en Go puro (`cmd/docgen`), diseñado para mantener la documentación técnica sincronizada, verificable y a prueba de enlaces rotos o desincronización de índices.

---

## 1. Topología Canónica del Directorio `docs/`

```text
docs/
├── ARCHITECTURE.md    # Síntesis arquitectural viva (Hexagonal, SOLID, Concurrencia, WAL)
├── BACKLOG.md         # Registro de fricción cero: defectos conocidos y mejoras diferidas
├── INDEX.md           # Índice autogenerado determinísticamente por cmd/docgen
├── decisions/         # ADRs inmutables con front-matter YAML (NNNN-kebab-slug.md)
├── rfcs/              # Propuestas y contratos formales con front-matter (NNNN-kebab-slug.md)
└── references/        # Documentos normativos, manuales CLI/TUI y especificaciones
```

---

## 2. Convenciones de Front-Matter YAML

Todo documento en `docs/decisions/` y `docs/rfcs/` debe iniciar con front-matter YAML delimitado por `---`:

```yaml
---
id: "0001"
title: "Persistencia SQLite Pure-Go con Wazero"
status: "accepted" # decisions: proposed, accepted, deprecated, superseded | rfcs: draft, proposed, accepted, implemented, rejected
created: "2026-11-15"
summary: "Adopción de ncruces/go-sqlite3 sin CGO para soporte multiplataforma determinista."
---
```

### Reglas de Validación:
1. **Identificador Canónico:** 4 dígitos numéricos con relleno (`0001` a `9999`). Debe coincidir exactamente con el prefijo del nombre de archivo (`0001-slug.md`).
2. **Fecha de Calendario:** Formato estricto `YYYY-MM-DD`, validado con `time.Parse("2006-01-02", date)`.
3. **Unicidad Global:** No pueden existir dos documentos con el mismo `id`, incluso entre carpetas distintas (`rfcs` y `decisions`).

---

## 3. Comandos de `cmd/docgen`

| Comando | Función |
| :--- | :--- |
| `go run ./cmd/docgen` | Recolecta todos los documentos, valida metadatos y enlaces, y regenera `docs/INDEX.md`. |
| `go run ./cmd/docgen --check` | Modo CI: Falla con código de salida 1 si `docs/INDEX.md` está desincronizado o hay enlaces rotos. |
| `go run ./cmd/docgen --next-id` | Imprime el siguiente ID secuencial disponible (ej. `0032`). |
| `go run ./cmd/docgen --new rfc <slug> --title "..."` | Crea atómicamente el scaffold `docs/rfcs/NNNN-<slug>.md` y regenera el índice. |
| `go run ./cmd/docgen --new decision <slug> --title "..."` | Crea el scaffold `docs/decisions/NNNN-<slug>.md` con front-matter canónico. |

---

## 4. Defensas de Seguridad y Validación de Enlaces

1. **Path Traversal Shield:** Todo enlace relativo (`[link](../path)`) se resuelve contra la raíz del repositorio (`FindDocsRoot`). Si intenta escapar de la frontera del repositorio (`../../../../etc/passwd`), el linter lo rechaza de inmediato.
2. **Prohibición de Rutas No Portables:** Quedan terminantemente prohibidos enlaces que utilicen `file://` o rutas absolutas iniciadas en `/`, garantizando que la documentación sea 100% portable entre máquinas de diferentes desarrolladores y servidores de CI.
3. **Escape de Caracteres en Tablas:** Todo pipe (`|`) o salto de línea en títulos o resúmenes se escapa determinísticamente a `\|` y espacios para no corromper las tablas de Markdown en `docs/INDEX.md`.
