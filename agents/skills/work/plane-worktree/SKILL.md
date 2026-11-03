---
name: plane-worktree
description: >-
  Orquesta Git worktrees multi-repo por ticket en .worktrees/<TICKET>-<SLUG>/.
  Úsalo para crear entornos de 2+ repos, listar (list) o auditar/podar entornos terminados (audit/prune).
  No usar para mono-repo (usar git) ni para tiempos/estados en Plane (usar plane-tracker).
---

# Multi-Repo Worktree Orchestrator (`plane-worktree`)

Gestión atómica de espacios de trabajo multi-repositorio por ticket (RFC 0002).

## Invariantes
- **Raíz:** Requiere `.worktrees/` en la raíz del workspace (`mkdir -p .worktrees`).
- **Atomicidad:** Pre-flight valida repos, `origin/<base>` y ramas antes de tocar disco. Si uno falla, aborta.
- **Ramas locales:** Si una rama existe y divergió de `origin/<base>`, aborta salvo que se pase `--reuse-branch`.
- **Fetch implícito:** `audit` y `prune` sincronizan `origin` en paralelo por repo único; usa `--no-fetch` para offline.
- **Nomenclatura:** Contenedor `.worktrees/<TICKET>-<SLUG>/`, ramas `<type>/<TICKET>-<SLUG_REPO>` (`feat|fix|spike|refactor|test|infra`).

## Comandos

| Acción | Comando |
| :--- | :--- |
| **Crear entorno** | `plane-worktree add <TICKET> <SLUG> <REPO1[=SLUG]> <REPO2>... [--type feat] [--base dev] [--reuse-branch] [--no-fetch]` |
| **Listar** | `plane-worktree list [--dir .worktrees] [--json]` (inspecciona ramas y dirty/clean) |
| **Auditar** | `plane-worktree audit [TARGET] [--no-fetch] [--json]` (detecta direct/squash merges y estado en SQLite) |
| **Poda dry-run** | `plane-worktree prune [TARGET] [--no-fetch] [--json]` (simulación sin tocar disco) |
| **Poda limpia** | `plane-worktree prune --execute [--no-fetch]` (elimina worktrees y ramas 100% integrados y limpios) |
| **Poda con respaldo** | `plane-worktree prune <TARGET> --execute --include-stale` (genera `.tar.gz` antes de borrar cancelados/stale) |

Detalles avanzados y respaldos en [GUIA_OPERATIVA_WORKTREES.md](file:///home/johantv/Code/dotfiles/agents/skills/work/plane-worktree/references/GUIA_OPERATIVA_WORKTREES.md).
