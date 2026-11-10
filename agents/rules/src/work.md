# Work Protocol and IT Tracking (Work Context)

### Communication and SDLC Scope:
- **User Language:** Always converse with the user in **Spanish** (conversational tone) unless explicitly instructed otherwise.
- **Environment:** Corporate repositories in `Code/` (`Omnify`, `Operaciones`, satellite services).
- **SDLC Phases:** `[SPIKE]` (diagnostic/investigation), `[RFC]` (design/contracts), `[FEAT/FIX/INFRA]` (development/devops), `[QA]` (testing/validation).

### Telemetry and Plane Tracking:
- **Tool:** Use `plane-tracker`. At session end or milestone completion, propose a concise worklog entry (≤700 chars, no markdown tables, no raw JSON; see `plane-tracker` §4) and post only after explicit user confirmation.
- **Toil & Meetings:** Absorb ad-hoc support and meetings into weekly umbrella tickets in `OPS`; never create tickets for tasks <15 min.

### Git Branching Conventions:
- **Corporate Pattern:** `{type}/{TICKET-ID}-{kebab-case-description}` (e.g. `feat/OMNIFY-175-campaign-validations`, `fix/OPS-44-mitigate-n8n`).
  - Types: `spike`, `feat`, `fix`, `refactor`, `test`, `infra`. Default project: `OMNIFY-` (`plane-tracker projects`).
- **Multi-Repo Initiatives:** When crossing 2+ repositories, do not create standalone branches; use `plane-worktree` in `.worktrees/{TICKET}-{slug}/`.
- **Ambiguity:** If no ticket is specified, clarify with user before creating the branch.
- **Personal / Non-Plane:** Standard `{type}/{kebab-case-description}`.

### Zero-Moment & Graduated Discovery:
- **Instant Search:** On work intent, run `plane-tracker list --text "<intent>" --all-projects --limit 5 --brief --json`. Conclude "no duplicate" only if `coverage.complete` is `true`.
  - Found: Confirm and switch to target branch (`feat/OMNIFY-XXX-...`).
  - Not found: Propose ticket with title, priority, labels, and `--branch-slug`.
- **Token Economy in CLI Queries:**
  - *Discovery:* `list --brief --json`.
  - *Selective Sync:* For ticket queries, use `plane-tracker sync tickets [-p PRJ]` (fast delta sync, ~1s). For general session/multi-machine sync (worklogs + tickets), use `plane-tracker sync --week --all-projects` (avoids 30-day default). Never use unconstrained `plane-tracker sync` without a period flag.
  - *Initial Inspection:* `plane-tracker get <TICKET>` (without `--full`, truncated to 300 chars).
  - *Deep Inspection:* Only when actively working on it, invoke `--full --no-comments` or `--last 3`. Never re-query data already in context.
- **Status Queries ("Revisa el Plane"):** Respond in **6-8 lines maximum**: Ticket/Title/State, contract summary, next step/stopper, and coverage notice.
- **Daily Report ("reporte del día"):** Run `plane-tracker report time --offline --all-projects` (<0.1s, SQLite). Present an executive summary (clock vs effort, AI Leverage) and a tabular chronological breakdown.

### Creation Standards and Ticket Lifecycle:
- **Title and Labels:** `[{PHASE}] {Concise action in Spanish}` (no nested brackets). Minimum 2 labels: technical layer (`backend`, `frontend`, `bd`, `infra`) and category (`bug`, `deuda-tecnica`, `seguridad`, `docs`); module label if applicable (`plane-tracker labels`).
- **Living Ticket Pattern (15-Minute Rule):**
  - `< 15 min (Toil):` Absorb into weekly `OPS` umbrella ticket.
  - `> 15 min:` Formal ticket. Description serves as a **living contract** (≤200 words, inverted pyramid: line 1 summary, root cause, 2-3 solution bullets, DoD checkboxes `[ ]`).
  - *No Circumstantial Evidence:* Raw SQL dumps, large tables, and code snippets belong in comments (`comment add`) or attachments (`attachment add`), never in ticket descriptions. If spawned from another issue, reference the source ID without duplicating text.
- **Weekly Umbrella Tickets (`OPS`, W{ISO_WEEK} cadence):**
  - Support: `Tareas Rápidas y Soporte - W{XX}` (`toil_support`).
  - Coordination: `Reuniones de Equipo y Acuerdos - W{XX}` (`coordination`).
  - Mandatory Dates: `--start-date` (Monday) and `--due-date` (Sunday).
  - Time Logging: `plane-tracker comment add <TICKET> --track "<topic>" --capacity "<bucket>" --duration <min>`. Never guess: ask real duration if performed outside the session.
- **Async Task Handoff Protocol:**
  - *Taking Over:* Run `plane-tracker get <TICKET>` to distill progress and stoppers. Log hours under own identity.
  - *Pausing / Handing Off:* Post a handoff comment detailing completed progress, current branch/commit, and immediate blockers.
