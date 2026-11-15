---
name: alo
description: Orquestador soberano Allostasis (`alo`) para tickets, estados, etiquetas, agenda y bitácoras de sesión contra Plane CE. Úsalo al iniciar/cerrar tareas, registrar horas, cambiar estados o consultar tickets.
---

# Allostasis Session Tracker & Worklog Operator (`alo`)

Procedimiento para operar Plane CE v1.2.3 (Omnify / Operaciones) y registrar telemetría de horas mediante el motor en Go de Allostasis (`alo`). Detalle en `references/GUIA_OPERATIVA_CLI_PLANE_TRACKER.md`.

## 0. Setup

Verifica la configuración y credenciales con `alo ticket whoami`. Si faltan variables de entorno, pide los valores al usuario (onboarding en `references/GUIA_OPERATIVA_CLI_PLANE_TRACKER.md` §0). Nunca expongas la API Key en logs ni chat.

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
| **Listar Tareas** | `alo ticket list [-p PROYECTO] [--mine] [--open] [--limit N] [--brief] [--json]` |
| **Detalle de Tarea** | `alo ticket get <TICKET-ID> [--json]` |
| **Crear Tarea** | `alo ticket create "<título>" [-p PROYECTO] [--priority Prioridad] [--state Estado] [--desc "Texto"] [--json]` |
| **Actualizar Tarea** | `alo ticket update <TICKET-ID> [--state Estado] [--priority Prioridad] [--title "Título"] [--json]` |
| **Eliminar Tarea** | `alo ticket delete <TICKET-ID> [--yes] [--discard-worklogs] [--json]` |
| **Listar Etiquetas** | `alo ticket labels` |
| **Registrar Telemetría/Horas** | `alo log <TICKET-ID> <DURACION_MINUTOS> [NOTAS...] [--bucket <bucket>] [--json]` |
| **Sincronizar Eventos y Outbox** | `alo sync [--limit N] [--json]` |
| **Sincronizar Catálogo Plane** | `alo ticket sync` |

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

## 7. Documentación y Backlog

- **Operación de Plane CE (Tickets corporativos y telemetría):**
  - Guías operativas en `references/`: guía operativa (`references/GUIA_OPERATIVA_CLI_PLANE_TRACKER.md`), living tickets y SDLC (`references/PROTOCOLO_LIVING_TICKETS_Y_SDLC.md`), relevo asíncrono (`references/PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md`), taxonomía y paraguas (`references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md`), arquitectura de telemetría (`references/ARQUITECTURA_SISTEMA_TRACKING_Y_TELEMETRIA.md`).
- **Desarrollo y Mantenimiento Interno del CLI (`alo`):**
  - Instrucciones para agentes de desarrollo: [`AGENTS.md`](./AGENTS.md) y arquitectura interna en [`ARCHITECTURE.md`](./ARCHITECTURE.md).
  - Backlog técnico interno: [`docs/BACKLOG.md`](./docs/BACKLOG.md).
  - Registro de arquitectura y propuestas: [`docs/INDEX.md`](./docs/INDEX.md) (ADRs en `docs/decisions/` y RFCs en `docs/rfcs/`) y principios en [`docs/principles.md`](./docs/principles.md).
  - Gobernanza y diseño del CLI: [`references/CLI_DESIGN_GUARD.md`](./references/CLI_DESIGN_GUARD.md).
  - *Regla clave:* Nunca busques ni crees tickets en Plane CE para bugs o deuda interna del propio CLI; esos temas residen en `docs/BACKLOG.md`.
