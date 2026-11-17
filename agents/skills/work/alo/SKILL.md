---
name: alo
description: Orquestador soberano Allostasis (`alo`) para tickets, estados, etiquetas, agenda, bitácoras de sesión contra Plane CE y orquestación atómica de Git worktrees multi-repo (`alo ws`). Úsalo al iniciar/cerrar tareas, registrar horas, cambiar estados, crear entornos de 2+ repos o podar worktrees.
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
- **Principio de Caja Negra:** El motor gestiona SQLite y caché internamente. Queda prohibido inspeccionar o consultar bases de datos locales por CLI.
- **Salida Estructurada:** Usa siempre `--json` en automatizaciones para parseo determinista sin ruido en `stderr`.
- **Aislamiento del Core:** NUNCA crees ni consultes tickets en Plane para bugs o refactorizaciones del propio CLI `alo` (pertenecen soberanamente al repositorio de `allostasis`).

## 2. CLI de Operaciones (`alo`)

Prefijos detectados automáticamente (`OMNIFY-162`, `OPS-44`).

### Tareas y Foco
```bash
alo ticket search "<texto>" [-p PROYECTO] [--limit N] [--json]
alo ticket list [-p PROYECTO] [--mine|--created|--involved] [--open] [-s ESTADOS] [--limit N] [--json]
alo ticket get <TICKET-ID> [--json]
alo ticket create "<título>" -p <PROYECTO> [--priority urgent|high|medium|low] [--state Estado] [--labels "a,b"] [--desc "Texto"] [--json]
alo ticket update <TICKET-ID> [--state Estado] [--priority Prioridad] [--title "Título"] [--json]
alo ticket focus [set <TICKET-ID> | clear | status]
alo ticket labels [-p PROYECTO] [--json]
alo ticket comment add <TICKET-ID> "<MENSAJE>" [--hours <float>] [--json]
```

- **Filtros Personales:**
  - `--mine`: Tareas asignadas a ti como responsable.
  - `--created`: Tareas creadas por ti.
  - `--involved`: Tareas en las que estás involucrado (asignadas, creadas o con actividad/horas tuyas).
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
alo sync [--json]
```

## 3. Reglas Corporativas de Gobernanza (Zero-Hop)

1. **Nomenclatura de Títulos (SDLC) & Responsabilidad Única:**
   - Formato obligatorio: `[{FASE}] {Acción concisa en español}`.
   - Fases canónicas: `[SPIKE]`, `[RFC]`, `[FEAT]`, `[FIX]`, `[INFRA]`, `[QA]`, `[REFACTOR]`.
   - *Responsabilidad Única:* PROHIBIDO mezclar `[FIX]` con mejoras de UX/producto (`[FEAT]`). Un bug fix repara exclusivamente la regresión/defecto.
   - *Etiquetas:* Mínimo 2 (`alo ticket labels`): Capa técnica (`backend`, `frontend`, `bd`, `infra`) + Tipo/Módulo (`bug`, `seguridad`, `sms`, `whatsapp`).
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
   - Declara explícitamente cualquier evidencia visual o log en `**Evidencias & Adjuntos:**`. Prohibido obligar al lector a adivinar o solicitar archivos a ciegas. Detalle de plantillas en `references/GOBERNANZA.md`.

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
