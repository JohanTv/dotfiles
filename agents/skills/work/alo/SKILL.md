---
name: alo
description: Orquestador soberano Allostasis (`alo`) para tickets, estados, etiquetas, agenda, bitácoras de sesión contra Plane CE y orquestación atómica de Git worktrees multi-repo (`alo ws`). Úsalo al iniciar/cerrar tareas, registrar horas, cambiar estados, crear entornos de 2+ repos o podar worktrees.
---

# Allostasis Session Tracker & Worklog Operator (`alo`)

Procedimiento para operar Plane CE v1.2.3 (Omnify / Operaciones) y registrar telemetría de horas mediante el motor en Go de Allostasis (`alo`). Directrices de gobernanza en [`references/`](references/README.md).

## 0. Setup

Verifica la configuración y credenciales con `alo ticket whoami`. Si faltan variables de entorno, pide los valores al usuario (`PLANE_BASE_URL`, `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`). Nunca expongas la API Key en logs ni chat.

## 1. Estados del ticket

Transiciones deterministas vía `alo ticket update <TICKET-ID> --state <Estado>`:
- `Pendiente` (sin iniciar) · `Progreso` (desarrollo/spike activo) · `Pruebas` (validando/tests) · `Revisión` (PR/staging esperando code review)
- `Pausado` (stopper externo) · `Completado` (mergeado/producción) · `Backlog` (idea/deuda) · `Cancelado` (descartado)

## 2. Proyectos y prioridades

- **Proyectos:** `OMNIFY` (código/plataformas), `OMNICANAL`, `OMNILEADS`, `CDP`, `OPS` (soporte y paraguas semanales; sin prefijo `[OPS]` en títulos).
- **Prioridades:** `urgent` (caídas/seguridad), `high` (sprint/bloqueo), `medium` (estándar), `low`/`none` (deuda menor).
- **Etiquetas:** `alo ticket labels` (mínimo 2: capa técnica + tipo). Taxonomía en `references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md`.

## 3. Comandos Nativos (`alo`)

Prefijos detectados por ticket (`OMNIFY-162`, `OPS-44`). Almacenamiento local y caché gestionados de forma interna e invisible por el motor de Allostasis (principio de caja negra).

| Tarea | Comando |
| :--- | :--- |
| **Diagnóstico y Conexión** | `alo ticket whoami [--json]` |
| **Agenda y Foco Activo** | `alo agenda [--json]` |
| **Auditoría de Carga (Toil)** | `alo load [--json]` |
| **Gestionar Foco de Sesión** | `alo ticket focus set <TICKET-ID>` · `alo ticket focus clear` · `alo ticket focus status` |
| **Buscar Tareas** | `alo ticket search "<texto>" [-p PROYECTO] [--limit N] [--json]` |
| **Listar Tareas** | `alo ticket list [-p PROYECTO] [--mine|--created|--involved] [--open] [--limit N] [--brief] [--verbose] [--json]` |
| **Listar Proyectos** | `alo projects [--json]` · `alo ticket projects [--json]` |
| **Listar Estados** | `alo states [-p PROYECTO] [--json]` · `alo ticket states [-p PROYECTO] [--json]` |
| **Detalle de Tarea** | `alo ticket get <TICKET-ID> [--json]` |
| **Crear Tarea** | `alo ticket create "<título>" [-p PROYECTO] [--priority Prioridad] [--state Estado] [--desc "Texto"] [--json]` |
| **Actualizar Tarea** | `alo ticket update <TICKET-ID> [--state Estado] [--priority Prioridad] [--title "Título"] [--json]` |
| **Eliminar Tarea** | `alo ticket delete <TICKET-ID> [--yes] [--discard-worklogs] [--json]` |
| **Listar Etiquetas** | `alo ticket labels` |
| **Registrar Telemetría/Horas** | `alo log <TICKET-ID> <DURACION_MINUTOS> [NOTAS...] [--bucket <bucket>] [--json]` |
| **Sincronizar Eventos y Outbox** | `alo sync [--limit N] [--json]` |
| **Sincronizar Catálogo Plane** | `alo ticket sync [-p PROYECTO] [--catalogs] [--all-projects]` |
| **Crear Entorno Multi-Repo** | `alo ws create <TICKET-ID> [SLUG] <REPO1> [REPO2...] [--type feat] [--base dev]` |
| **Listar Entornos Activos** | `alo ws list [--dir .worktrees] [--json]` |
| **Auditar Integración Git/Plane** | `alo ws audit [TARGET] [--no-fetch] [--json]` |
| **Podar Worktrees Terminados** | `alo ws prune [--execute] [--include-stale] [--json]` |

- **Modo Desconectado / Resiliencia:** Si Plane no responde, las operaciones se registran localmente. Al reconectar, ejecuta `alo sync` para procesar y vaciar los eventos pendientes del outbox diferido.
- **Refresco de Tareas:** Para actualizar la copia local de tareas y proyectos desde Plane, ejecuta `alo ticket sync`.

## 4. Registro de Sesión y Telemetría

Registra el esfuerzo de la sesión mediante el comando nativo `alo log`:
```bash
alo log <TICKET-ID> <DURACION_MINUTOS> "[NOTAS...]" --bucket <bucket>
```

Reglas:
1. **Duración en Minutos:** Indica los minutos exactos invertidos en la sesión (pregunta al usuario o mide el tiempo transcurrido; nunca inventes cifras).
2. **Notas Estructuradas:** Breve resumen en 1 a 3 viñetas (Hecho, Evidencia/PR, Bloqueos).
3. **Buckets de Capacidad (`--bucket`):**
   - `deep_work` (por defecto): Desarrollo de funcionalidades, refactorización profunda o spikes.
   - `toil_support`: Soporte reactivo, atención a incidencias o mantenimiento operativo.
   - `coordination`: Reuniones, ceremonias de equipo o coordinación técnica.
   - `standby`: Espera activa o bloqueos externos.
4. **Sincronización:** Ejecuta `alo sync` para subir los eventos diferidos al servidor de Plane CE.

## 5. Relevo entre Sesiones

- **Dejar Tarea en Pausa:** Si la tarea queda incompleta, actualiza el estado con `alo ticket update <TICKET-ID> --state Pausado`, libera el foco con `alo ticket focus clear` y registra el progreso con `alo log <TICKET-ID> <MINUTOS> "Relevo: <resumen de avance>"`.
- **Retomar Tarea:** Consulta el detalle con `alo ticket get <TICKET-ID>`, marca el foco activo con `alo ticket focus set <TICKET-ID>` y actualiza el estado con `alo ticket update <TICKET-ID> --state Progreso`.

## 6. Crear work items

- **Título:** `[{FASE}] {acción o resumen conciso en español}` (`[SPIKE]`, `[RFC]`, `[FEAT]`, `[FIX]`, `[INFRA]`, `[QA]`, `[REFACTOR]`).
- **Etiquetas (mínimo 2):** Capa técnica (`backend`, `frontend`, `bd`, `infra`) y tipo (`bug`, `deuda-tecnica`, `seguridad`, `docs`).
- **Contrato vivo:** Descripción ≤ 200 palabras (Resumen, Causa, Solución, DoD `[ ]`). Detalle en `references/PROTOCOLO_LIVING_TICKETS_Y_SDLC.md`.

## 7. Gobernanza Corporativa y Desarrollo del Core

- **Gobernanza Operativa de Plane CE:**
  - Directrices vivas en [`references/`](references/README.md): Living tickets y ciclo SDLC (`PROTOCOLO_LIVING_TICKETS_Y_SDLC.md`), relevo asíncrono (`PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md`), taxonomía y tickets paraguas (`MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md`), y estrategia de capacidad (`ESTRATEGIA_GESTION_TI_Y_WORKITEMS.md`).
  - Gobernanza y diseño del CLI: [`CLI_DESIGN_GUARD.md`](references/CLI_DESIGN_GUARD.md).
- **Desarrollo y Mantenimiento del Motor en Go (`allostasis`):**
  - El código fuente, la arquitectura hexagonal, los RFCs/ADRs y las directrices de ingeniería (`AGENTS.md`, `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`) residen de forma soberana en el repositorio del proyecto `allostasis`.
  - *Regla de Aislamiento:* NUNCA busques, consultes ni crees tickets en Plane CE para bugs, deuda o refactorizaciones internas del propio CLI `alo`; esos temas pertenecen al repositorio de `allostasis`.

## 8. Orquestación de Git Worktrees Multi-Repo (`alo ws`)

Gestión atómica y transaccional de espacios de trabajo multi-repositorio por ticket, respaldada por el motor nativo de Allostasis:

### Invariantes:
- **Raíz:** Requiere contenedor `.worktrees/` en la raíz del workspace (`mkdir -p .worktrees`).
- **Atomicidad Transaccional:** Pre-flight valida repos, `origin/<base>` y ramas antes de tocar disco. Si uno falla, aborta y revierte sin residuos.
- **Ramas locales:** Si una rama existe y divergió de `origin/<base>`, aborta salvo que se pase `--reuse-branch`.
- **Fetch implícito:** `audit` y `prune` sincronizan `origin` en paralelo por repo único; usa `--no-fetch` para modo offline.
- **Nomenclatura:** Contenedor `.worktrees/<TICKET>-<SLUG>/`, ramas `<type>/<TICKET>-<SLUG_REPO>` (`feat|fix|spike|refactor|test|infra`).

### Comandos de Worktrees:
```bash
# Crear entorno multi-repo vinculado a un ticket
alo ws create <TICKET-ID> [SLUG] <REPO1> [REPO2...] [--type feat] [--base dev]

# Listar contenedores activos y estado de dirty/clean
alo ws list [--json]

# Auditar integrabilidad con Git y estado del ticket en Plane
alo ws audit [TARGET] [--no-fetch] [--json]

# Simular poda segura (dry-run por defecto)
alo ws prune [--no-fetch]

# Ejecutar poda limpia de ramas 100% integradas
alo ws prune --execute

# Podar tickets cancelados/abandonados con respaldo comprimido .tar.gz
alo ws prune [TARGET] --execute --include-stale
```
