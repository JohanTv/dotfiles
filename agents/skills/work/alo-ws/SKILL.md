---
name: alo-ws
description: >-
  Orquesta Git worktrees multi-repo por ticket en .worktrees/<TICKET>-<SLUG>/.
  Úsalo para crear entornos de 2+ repos (alo ws create), listar (alo ws list) o auditar/podar entornos terminados (alo ws audit, alo ws prune).
---

# Multi-Repo Worktree Orchestrator (`alo ws`)

Gestión atómica y transaccional de espacios de trabajo multi-repositorio por ticket, respaldada por el motor nativo en Go de Allostasis (`alo ws`).

## Invariantes
- **Raíz:** Requiere `.worktrees/` en la raíz del workspace (`mkdir -p .worktrees`).
- **Atomicidad:** Pre-flight valida repos, `origin/<base>` y ramas antes de tocar disco. Si uno falla, aborta y hace rollback sin residuos.
- **Ramas locales:** Si una rama existe y divergió de `origin/<base>`, aborta salvo que se pase `--reuse-branch`.
- **Fetch implícito:** `audit` y `prune` sincronizan `origin` en paralelo por repo único; usa `--no-fetch` para offline.
- **Nomenclatura:** Contenedor `.worktrees/<TICKET>-<SLUG>/`, ramas `<type>/<TICKET>-<SLUG_REPO>` (`feat|fix|spike|refactor|test|infra`).

## Comandos Nativos (`alo ws`)

| Acción | Comando |
| :--- | :--- |
| **Crear entorno** | `alo ws create <TICKET-ID> [SLUG] <REPO1> [REPO2...] [--type feat] [--base dev]` |
| **Listar** | `alo ws list [--dir .worktrees] [--json]` (inspecciona ramas y dirty/clean) |
| **Auditar** | `alo ws audit [TARGET] [--no-fetch] [--json]` (detecta direct/squash merges en memoria y estado local) |
| **Poda dry-run** | `alo ws prune [TARGET] [--no-fetch] [--json]` (simulación sin tocar disco por defecto) |
| **Poda limpia** | `alo ws prune --execute [--no-fetch]` (elimina worktrees y ramas 100% integrados y limpios) |
| **Poda con respaldo** | `alo ws prune [TARGET] --execute --include-stale` (genera `.tar.gz` antes de borrar cancelados/stale) |

Detalles avanzados y respaldos en [GUIA_OPERATIVA_WORKTREES.md](file:///home/johantv/Code/dotfiles/agents/skills/work/alo-ws/references/GUIA_OPERATIVA_WORKTREES.md).
