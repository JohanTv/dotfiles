# Large Codebase Taming

Peripheral noise (generated code, mocks, fixtures, snapshots, bundles) and blind exploration consume agent context. Raise exclusion walls and pin navigation.

## 1. Measure the noise first
- `fd -t f | wc -l` vs `rg --files | wc -l` shows what current filters already hide.
- For each candidate pattern, confirm it matches what you think: `rg --files | rg '<pattern>'` (or `fd`). Never add a pattern unverified.

## 2. Tool wall (ignore files)
Candidate patterns to audit per repo, not to paste blindly:

| Candidate | Hazard to check |
| :--- | :--- |
| `**/*_gen.*`, `**/*.pb.go`, `**/generated/**` | Usually safe; confirm they are really generated |
| `**/mocks/**`, `**/mock_*.go`, `**/__snapshots__/**`, `**/cassettes/**`, `**/testdata/fixtures/**` | Hand-written test helpers may live there |
| `**/swagger/**`, `**/openapi/**` | Often hold **hand-authored specs** (source of truth); ignore only generated stubs |
| `**/dist/**`, `**/build/**`, `**/.next/**`, `**/target/**` | `build/` may hold scripts or Dockerfiles |
| `**/vendor/**` | Vendored deps may be needed when debugging them |
| `*.log`, `*.sqlite*`, `*.db*`, `.cache/` | Safe in most repos |

Files: `.ignore` (rg + fd), `.rgignore`, `.fdignore`.

**Shared vs local.** A committed `.ignore` changes behavior for the whole team. In shared or corporate repos, prefer a local-only wall: patterns in `.git/info/exclude` (rg/fd honor git ignore rules; verify empirically with `rg --files | rg '<pattern>'`), or a personal global ignore config. Committing `.ignore` requires approval (gate in SKILL.md).

## 3. Intentional bypass protocol
If the user explicitly asks to inspect, audit or modify a file in an ignored zone, never assume it does not exist. Disable the filter for that search (`rg --no-ignore`, `rg -u`, `fd --no-ignore`).

## 4. Cognitive wall
In the instruction file, list auxiliary folders the agent must not explore or read autonomously unless the user explicitly asks (e.g. `generated/`, `test/fixtures/`, `vendor/`). Keep it to one line per zone.

## 5. Hierarchical routing (Map & Dispatch)
- **Shallow map:** root doc exposes the tree to depth ≤ 2 with a one-line responsibility per module. No deep trees.
- **Entrypoint pinning:** name the 1-3 files that bootstrap/wire the system (main, DI container, main router). Removes initial exploratory searches.
- **Scoped search:** once the task domain is known, search only the relevant path, not the whole repo.
- **Monorepo router:** root file keeps global invariants plus a routing table; module-level instruction files load only when working in that module.

### Router template
```md
# Agent Instructions: [System]

> Global invariants and routing. Load module guidance on demand.

## Global Invariants
1. [cross-cutting build/language rule]
2. [cross-cutting test/safety rule]

## Domain Routing
| Module | Path | Module guidance | Entrypoints |
| :--- | :--- | :--- | :--- |
| API | `services/api` | `services/api/AGENTS.md` | `cmd/server/main.go` |

## Ignored Zones (do not explore)
`generated/`, `test/fixtures/`, `vendor/`
```

## 6. Verify
- Re-run the noise measurement: count dropped, and no hand-written source disappeared (spot-check with `rg --files | rg '<expected-file>'`).
- Test the bypass: an ignored file is reachable with the bypass flag.
