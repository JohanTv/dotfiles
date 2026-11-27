---
name: alo
description: Orquestador soberano Allostasis (`alo`) para tickets, estados, etiquetas, adjuntos, enlaces, comentarios, agenda, bitácoras de sesión contra Plane CE y orquestación atómica de Git worktrees multi-repo (`alo ws`). Úsalo al iniciar/cerrar tareas, registrar horas, cambiar estados, adjuntar evidencias, sincronizar con Plane, crear entornos de 2+ repos o podar worktrees.
---

# Allostasis Session Tracker & Worklog Operator (`alo`)

Procedimiento operativo para Plane CE v1.2.3 y telemetría de horas mediante Allostasis (`alo`).

## 0. Disparadores de Carga Condicional (Lazy-Loading)

> [!IMPORTANT]
> **REGLA DE CARGA PEREZOSA:** NO leas la carpeta `references/` por defecto.
> - Lee [`references/GOBERNANZA.md`](references/GOBERNANZA.md) **ÚNICAMENTE SI:**
>   1. Vas a crear o redactar la descripción de un ticket nuevo (`alo ticket create`) y requieres consultar las plantillas exhaustivas por fase (`[SPIKE]`, `[RFC]`, `[FEAT/FIX]`).
>   2. El usuario pide auditar o abrir los tickets paraguas semanales `OPS` de la semana ISO `W{XX}`.
>   3. Necesitas transferir un ticket ajeno o publicar un relevo formal de salida (`Handoff Snapshot`).

## 1. Setup y Principios Innegociables

- **Diagnóstico:** `alo ticket whoami [--json]`. Si faltan credenciales, solicita al usuario `PLANE_BASE_URL`, `PLANE_API_KEY` y `PLANE_WORKSPACE_SLUG`. Nunca expongas secretos.
- **Caja Negra & DBs:** Prohibido alterar DBs para puentear fallos. Consultas directas (`sqlite3`) permitidas para diagnóstico/auditoría bajo autorización, en solo lectura y sin exponer secretos.
- **Salida Estructurada:** Usa siempre `--json` en automatizaciones para parseo determinista sin ruido en `stderr`.
- **Lecturas locales, red solo en `sync`:** toda lectura (`list`, `get`, `search`, `labels`, `states`, `comment list`, `attachment list`, `link list`, `get --include`) lee SQLite sin red y funciona offline. Refrescar contra Plane es siempre un comando explícito de `alo sync` (ver "Lecturas locales, sincronización y mutaciones diferidas").
- **Aislamiento del Core:** NUNCA crees ni consultes tickets en Plane para bugs o refactorizaciones del propio CLI `alo` (pertenecen soberanamente al repositorio de `allostasis`).

## 2. CLI de Operaciones (`alo`)

Prefijos detectados automáticamente (`OMNIFY-162`, `OPS-44`).

### Tareas y Foco
```bash
alo ticket search "<texto>" [-p PROYECTO] [--limit N] [--json]
alo ticket list [-p PROYECTO] [--mine|--created|--involved] [--closed|--all] [-s ESTADOS] [--limit N] [--json]
alo ticket get <TICKET-ID> [--include comments,history,attachments,links] [--last N] [--json]
alo ticket create "<título>" -p <PROYECTO> [--priority urgent|high|medium|low] [--state Estado] [--labels "a,b"] [--desc "Texto"] [--attach archivo]... [--json]
alo ticket update <TICKET-ID> [--state Estado] [--priority Prioridad] [--title "Título"] [--labels "a,b"] [--json]
alo ticket focus [set <TICKET-ID> | clear | status]
alo ticket labels [-p PROYECTO] [--json]
alo states [-p PROYECTO] [--json]
alo ticket comment add <TICKET-ID> "<MENSAJE>" [--hours <float>] [--json]
alo ticket comment list <TICKET-ID> [--last N] [--json]
alo ticket attachment add <TICKET-ID> <ARCHIVO>... [--json]
alo ticket attachment list <TICKET-ID> [--json]
alo ticket attachment replace <TICKET-ID> <ATTACHMENT-ID> <ARCHIVO> [--json]
alo ticket attachment delete <TICKET-ID> <ATTACHMENT-ID> --yes [--json]
alo ticket link add <TICKET-ID> <URL> [--title "..."] | list <TICKET-ID> | delete <TICKET-ID> <LINK-ID>
```

- **Filtros Personales & Modificadores de Estado:**
  - `list` muestra por defecto solo **tareas abiertas** (*Open-by-Default*).
  - `--mine`: Tareas asignadas a ti como responsable.
  - `--created`: Tareas creadas por ti.
  - `--involved`: Tareas en las que estás involucrado (asignadas, creadas o con actividad/horas tuyas).
  - `--closed`: Filtrar exclusivamente tareas cerradas (completadas o canceladas).
  - `--all` / `--all-states`: Desactivar filtro de abiertas y mostrar todo el universo de tareas.
  - `-s ESTADOS`: Filtro explícito de estado (ej. `-s Completado`); prevalece sobre el default de abiertas.
- **Estados Válidos:** `Pendiente`, `Progreso`, `Pruebas`, `Revisión`, `Pausado`, `Completado`, `Backlog`, `Cancelado`.
- **Proyectos Canónicos:** `OMNIFY` (desarrollo/plataformas), `OPS` (operaciones y soporte paraguas), `OMNICANAL`, `OMNILEADS`, `CDP`.

### Telemetría, Diagnóstico y Sincronización
```bash
# Registrar esfuerzo de sesión (minutos reales invertidos; nunca inventar)
alo log <TICKET-ID> <MINUTOS> "[NOTAS]" --bucket <deep_work|toil_support|coordination|standby> [--json]

# Diagnóstico de carga y agenda activa
alo load [--json]    # Ratio de toil/soporte reactivo vs trabajo profundo
alo agenda [--json]  # Focos y tareas activas del día

# Sincronización bidireccional (procesa outbox diferido y delta pull)
alo sync [all|tickets|catalogs|outbox|hours] [--json]

# Recursos hijos de UN ticket (la única vía de red para leerlos frescos)
alo sync attachments <TICKET-ID> [--json]
alo sync links <TICKET-ID> [--json]
alo sync comments <TICKET-ID> [--json]
```

### Lecturas locales, sincronización y mutaciones diferidas

- **Forma de los listados** (`attachment list`, `link list`, `comment list`, `labels`, `states` y las secciones de `get --include`): `{schema, view, scope, count, results[], coverage}`. Itera `.data.results[]`, no `.data[]`.
- **`coverage`** dice cuánto fiarte de los datos: `source` (`cache` en lecturas, `api` justo tras un `sync`), `as_of` y `age_s` (cuándo se sincronizó y qué antigüedad tiene; `null` si nunca), `complete` (`null` = nunca sincronizado) y `reason` (`never_fetched` o `local_ticket`).
  - **Una lista vacía con `reason: never_fetched` NO significa "no hay elementos"**: ejecuta el comando que indica `coverage.note` (`alo sync attachments|links|comments <TICKET>`, o `alo sync catalogs` para etiquetas y estados) antes de concluir nada.
  - Decide tú si la antigüedad (`age_s`) basta; no hay caducidad automática.
- **Mutaciones diferidas:** `ticket create` y `ticket update` sin conexión (o con Plane caído) quedan en el outbox y devuelven `pending_sync: true`; no están en Plane hasta `alo sync outbox`. Revisa la cola con `alo ticket outbox list`. La creación en cola lleva una clave de idempotencia: **no la repitas**, el reintento adopta lo que Plane ya tenga.
- **Requieren conexión y NO se encolan:** adjuntos (`attachment add|replace|delete`, `create --attach`), enlaces y `comment edit|delete`. Sin conexión fallan a la vista.
- **Validación contra el catálogo:** etiquetas y estados se resuelven desde el catálogo local; uno inexistente es un error de uso con la lista de válidos. Si el catálogo está vacío, `alo sync catalogs`.
- **`ticket create --attach`:** valida todos los archivos y exige credenciales *antes* de crear; después sube cada archivo. Si una subida falla, **la tarea ya existe**.

### Contrato de errores (`--json`)

Un fallo sale como `{"ok": false, "error": {code, category, hint, suggested_command, recoverable, context}}` por `stdout` (`stderr` queda vacío). El código de salida deriva de `error.category`:

| Exit | `category` | Qué hacer |
| :---: | :--- | :--- |
| `0` | — | Éxito |
| `2` | `user_input` | Uso o datos inválidos (flag, etiqueta o estado inexistente, archivo inválido, sin credenciales): corrige según `hint`/`suggested_command` |
| `3` | `auth` | Credenciales o permisos: `alo ticket whoami` |
| `4` | `not_found` | El recurso no existe (ticket inexistente) |
| `5` | `upstream_service` | Plane no respondió: reintenta; las lecturas locales siguen funcionando |
| `6` | `state_conflict` | El estado actual impide la operación (conflicto de merge, prerrequisito) |
| `1` / `70` | `internal` / pánico | Fallo de ejecución o error sin clasificar: repórtalo, no lo ignores |

- **Confirmación:** los destructivos exigen `--yes` (`ticket delete`, `comment delete`, `attachment delete`). Sin él devuelven `CONFIRMATION_REQUIRED` con el `suggested_command` exacto.
- **Fallo parcial al crear con adjuntos o en cola** (`ATTACHMENT_PARTIAL`, `CREATE_PENDING_SYNC`): la tarea **ya existe**, aunque el comando salga con error. **NO ejecutes `create` otra vez** (duplicarías la tarea): toma la clave de `error.context.created` y sigue `suggested_command` (`alo ticket attachment add <KEY> <archivo>` o `alo sync`).
- Un subcomando desconocido (`alo ticket nope`) es exit 2, no ayuda con éxito.

## 3. Reglas Corporativas de Gobernanza (Zero-Hop)

1. **Nomenclatura de Títulos (SDLC) & Responsabilidad Única:**
   - Formato obligatorio: `[{FASE}] {Acción concisa en español}`.
   - Fases canónicas: `[SPIKE]`, `[RFC]`, `[FEAT]`, `[FIX]`, `[INFRA]`, `[QA]`, `[REFACTOR]`.
   - *Responsabilidad Única:* PROHIBIDO mezclar `[FIX]` con mejoras de UX/producto (`[FEAT]`). Un bug fix repara exclusivamente la regresión/defecto.
   - *Etiquetas:* Mínimo 2 (`alo ticket labels`; deben existir en Plane, si no `create`/`update` fallan con la lista de válidas): Capa técnica (`backend`, `frontend`, `bd`, `infra`) + Tipo/Módulo (`bug`, `seguridad`, `sms`, `whatsapp`).
2. **Regla de los 15 Minutos & Transición desde `OPS`:**
   - **< 15 min (Toil / Soporte Rápido / Dailies):** Imputar al ticket paraguas semanal de `OPS` (`Soporte y Mantenimiento Ad-Hoc - W{XX}` o `Sincronización de Equipo - W{XX}`) vía `alo log OPS-XX <MINUTOS> --bucket toil_support|coordination`.
   - **> 15 min (Regla de Transición):** Si una tarea en `OPS` supera los 15m, detén la imputación en `OPS`, abre de inmediato el ticket formal en `OMNIFY` y transfiere el esfuerzo acumulado desde el minuto 0 al nuevo ticket vía `alo log <TICKET> <MINUTOS> --bucket deep_work`.
3. **Pausa y Relevo Asíncrono (Handoff Snapshot):**
   - Al pausar o transferir: transicionar a `Pausado`, liberar foco (`alo ticket focus clear`) y publicar comentario con:
     ```bash
     alo ticket comment add <ID> "### 🔄 Relevo de Tarea (Handoff Snapshot)
     - **Avance realizado:** Resumen conciso de lo construido o diagnosticado.
     - **Rama Git / Commit:** {tipo}/{TICKET-ID}-{kebab} @ {hash}.
     - **Estado actual:** Componentes estables y verificados.
     - **Stoppers / Próximo paso:** Siguiente acción inmediata sin perder el hilo."
     ```
4. **Pirámide Invertida & Evidencias Declaradas:**
   - Al crear o actualizar tickets (`alo ticket create "<título>" --desc "..."`), la descripción DEBE seguir el siguiente esqueleto canónico:
     ```markdown
     **Resumen:** [1 oración de intención completa y autosuficiente].
     **Contexto & Causa:** [Componentes exactos, PR upstream, endpoints o síntoma].
     **Evidencias & Adjuntos:** [screenshots/*.png, enlace Figma, o "Ver comentario #1"].
     **Solución / Opciones a Evaluar:** [Solución si es conocida; Opciones o Hipótesis si está en análisis].
     **Criterio de Cierre:** [DoD [ ] para FEAT/FIX; Checklist/Veredicto para SPIKE/RFC].
     ```
   - **Flexibilidad en Incertidumbre:** Si el ticket es un `[SPIKE]` o la causa no está aislada, NUNCA inventes una solución prematura; lista `**Opciones a Evaluar:**` o `**Hipótesis:**` (como en `OMNIFY-274`).
   - **DoD Desacoplado de Entorno Local:** El DoD (`- [ ]`) debe validar entregables verificables, contratos y tests (`npm run check`, `go test`). PROHIBIDO incluir comandos efímeros locales (como `alo ws create`) en el DoD.
   - Cita siempre identificadores técnicos reales (`CampaignChipFloatingMenu`, `PR #265`, etc.).
   - Declara explícitamente cualquier evidencia visual o log en `**Evidencias & Adjuntos:**`. Prohibido obligar al lector a adivinar o solicitar archivos a ciegas. **Adjunta la evidencia de verdad** con `alo ticket create ... --attach <archivo>` o `alo ticket attachment add <TICKET-ID> <archivo>` (máx. 50 MB; `.sql` no se admite: renómbralo a `.txt`/`.md`). Detalle de plantillas en `references/GOBERNANZA.md`.

## 4. Git Worktrees Multi-Repo (`alo ws`)

Gestión atómica y transaccional respaldada por Allostasis:

### Invariantes:
- **Directorio:** Requiere raíz `.worktrees/<TICKET>-<SLUG>/` (`mkdir -p .worktrees`).
- **Atomicidad Transaccional:** Validación pre-flight (repos, `origin/<base>`, ramas). Si falla, aborta y revierte sin residuos en disco.
- **Nomenclatura de Ramas:** `<type>/<TICKET>-<SLUG_REPO>` (`feat|fix|spike|refactor|test|infra`).
- **Ramas Locales:** Si divergió de `origin/<base>`, aborta salvo indicación explícita.

### Comandos:
```bash
alo ws create <TICKET-ID> [SLUG] <REPO1> [REPO2...] [--type feat] [--base main]
alo ws list [--json]
alo ws audit [TARGET] [--no-fetch] [--json]
alo ws prune [--execute] [--include-stale] [--no-fetch] [--json]
```
