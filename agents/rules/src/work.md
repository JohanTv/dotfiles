# Protocolo de Trabajo y Tracking TI (Work Context)

### Ámbito y Fases (SDLC):
- **Entorno:** Repositorios corporativos en `Code/` (`Omnify`, `Operaciones`, servicios satélite).
- **Fases:** `[SPIKE]` (diagnóstico/forense), `[RFC]` (diseño/contratos), `[FEAT/FIX/INFRA]` (desarrollo/devops), `[QA]` (testing/validación).

### Telemetría y Registro en Plane:
- **Skill:** Usa `plane-tracker`. Al finalizar sesión o hito, propón bitácora corta (≤700 caracteres, sin tablas ni JSON; ver `plane-tracker` §4) y publica solo tras OK.
- **Toil y Reuniones:** Absorbe soporte ad-hoc y reuniones en los tickets paraguas semanales de `OPS`; nunca crees tickets <15 min.

### Convención de Ramas Git:
- **Patrón Corporativo:** `{tipo}/{TICKET-ID}-{kebab-case-descripcion}` (ej: `feat/OMNIFY-175-campaign-validations`, `fix/OPS-44-mitigate-n8n`).
  - Tipos: `spike`, `feat`, `fix`, `refactor`, `test`, `infra`. Default: `OMNIFY-` (proyectos en `plane-tracker projects`).
- **Iniciativas Multi-Repo:** Si cruza 2+ repos, no crees ramas sueltas; usa la skill `plane-worktree` en `.worktrees/{TICKET}-{slug}/`.
- **Manejo de Ambigüedad:** Si no se menciona el ticket, pregunta antes de crear la rama.
- **Personal / Sin Plane:** Usa formato estándar `{tipo}/{kebab-case-descripcion}`.

### Momento Cero y Lectura Escalonada:
- **Búsqueda Instantánea:** Ante una intención de trabajo, ejecuta `plane-tracker list --text "<intención>" --all-projects --limit 5 --brief --json`. Solo concluye "no hay duplicado" si `coverage.complete` es `true`.
  - Coincidente: Confirma y pasa a la rama respectiva (`feat/OMNIFY-XXX-...`).
  - No existe: Propón work item con título, prioridad, etiquetas y `--branch-slug`.
- **Economía de Tokens en Consultas:**
  - *Descubrimiento:* `list --brief --json`.
  - *Sincronización Selectiva:* Si se necesita refrescar tickets desde Plane, usa `plane-tracker sync tickets [-p PRJ]` (delta sync ligero, ~1s); nunca uses `plane-tracker sync` completo (que descarga 30 días de horas) para una consulta de tickets.
  - *Inspección inicial:* `plane-tracker get <TICKET>` (sin `--full`, truncado a 300 caracteres).
  - *Profunda:* Solo al trabajar activamente en él, invoca `--full --no-comments` o `--last 3`. No re-pidas datos ya en contexto.
- **Consultas de Estado ("Revisa el Plane"):** Responde en **6-8 líneas máximo**: Ticket/Título/Estado, resumen del contrato, siguiente paso/stopper y advertencia de `coverage`.
- **Informe del Día:** Ante resumen de jornada ("mi informe de hoy", "reporte del día"), ejecuta directo `plane-tracker report time --offline --all-projects` (<0.1s, SQLite). Presenta consolidado ejecutivo (reloj vs esfuerzo, AI Leverage) y cronología tabular.

### Estándar de Creación y Ciclo de Vida:
- **Título y Etiquetas:** `[{FASE}] {Acción o resumen conciso en español}` (sin corchetes dobles). Mínimo 2 etiquetas: capa técnica (`backend`, `frontend`, `bd`, `infra`) y tipo (`bug`, `deuda-tecnica`, `seguridad`, `docs`); módulo si aplica (`plane-tracker labels`).
- **Living Ticket Pattern (Regla de los 15 Minutos):**
  - `< 15 min (Toil):` Absorbe en ticket paraguas semanal de `OPS`.
  - `> 15 min:` Ticket formal. Descripción es el **contrato vivo** (≤200 palabras, pirámide invertida: Resumen primera línea, Causa, Solución en 2-3 viñetas, DoD `[ ]`).
  - *Sin evidencia circunstancial:* Dumps SQL, tablas y snippets van en comentarios (`comment add`) o adjuntos (`attachment add`), nunca en la descripción. Si deriva de otro ticket, referencia origen sin duplicar texto.
- **Tickets Paraguas Semanales (`OPS`, cadencia W{ISO_WEEK}):**
  - Soporte: `Tareas Rápidas y Soporte - W{XX}` (`toil_support`).
  - Coordinación: `Reuniones de Equipo y Acuerdos - W{XX}` (`coordination`).
  - Fechas obligatorias: `--start-date` (lunes) y `--due-date` (domingo).
  - Registro: `plane-tracker comment add <TICKET> --track "<tema>" --capacity "<balde>" --duration <min>`. Nunca estimes: pregunta duración real si fue fuera de sesión.
- **Protocolo de Relevo Asíncrono (Task Handoff):**
  - *Tomar ticket ajeno:* `plane-tracker get <TICKET>` para destilar avances y stoppers. Imputa horas a nombre propio.
  - *Dejar tarea a medias:* Publica comentario de relevo (avance, rama/commit actual, pendientes inmediatos).
