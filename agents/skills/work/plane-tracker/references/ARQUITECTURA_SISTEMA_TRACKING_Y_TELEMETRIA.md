# 🏛️ Arquitectura del Sistema de Tracking, Telemetría y Gestión de Work Items
## Especificación Maestra de Ingeniería para Plane CE v1.2.3 en Flujos Asistidos por IA (agy, Claude Code, OpenCode)

**Autor:** Johan Tanta & Asistente Orquestador (DeepMind Antigravity)  
**Fecha:** 29 de Octubre de 2026 | **Versión:** 2.4.0 (FTS5 + Klee Interval Merging + Handoff Engine)  
**Entorno:** Ubuntu Linux (WSL) / Host Nativo | **Perfil Dotfiles:** `work`  
**Instancia Plane:** `http://190.105.240.58` (Workspace: `teamprogra` | Proyecto Core: `OMNIFY` | Operaciones: `OPS`)  
**Base de Datos Local:** `~/.cache/plane/worklogs.db` (SQLite3 con WAL Mode)

---

## 1. Visión General y Filosofía de Diseño

El sistema resuelve la desconexión crítica entre el **desarrollo acelerado por IA** (donde un ingeniero senior opera con subagentes y múltiples sesiones concurrentes) y la **gestión administrativa de TI** (reportes diarios a jefatura, seguimiento en Kanban y justificación de tiempos).

```
┌────────────────────────────────────────────────────────────────────────┐
│ claude.ai (Nube Anthropic / Web o Móvil)                              │
│ ➔ Gestión macro de producto, backlog refinement, consultas ad-hoc       │
│ ➔ Conector remoto HTTPS / SSE (OMNIFY-197)                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Petición HTTP / SSE)
                                    ▼
                         [ Servidor Plane CE v1.2.3 ]
                                    ▲
                                    │ (API REST + Sync On-Demand)
┌───────────────────────────────────┴────────────────────────────────────┐
│ Tu Estación Local (Terminal / agy / Claude Code / OpenCode)            │
│ ➔ Motor Local-First en SQLite3 WAL (~/.cache/plane/worklogs.db)        │
│ ➔ Búsqueda Momento Cero FTS5 (< 2ms)                                  │
│ ➔ Interval Merging de Klee (Lebesgue 1D) para fusión de concurrencia   │
│ ➔ Protocolo de Relevo Asíncrono (Task Handoff con Pierre/equipo)       │
│ ➔ Reporte Diario a Jefatura a las 6:00 pm (0.08s, sin IA, 0 tokens)    │
└────────────────────────────────────────────────────────────────────────┘
```

### Principios Fundamentales:
1. **Local-First con Zero-Latency:** Las consultas de etiquetas, proyectos, búsqueda de tickets y registro de sesiones responden en **< 2 milisegundos** desde SQLite local. La red solo se utiliza para transiciones oficiales de estado y publicación de bitácoras.
2. **Dual-Layer Information Standard:** Todo evento registrado hacia Plane contiene una tabla visual limpia para lectura humana (Pierre, gerencia) y un bloque JSON estructurado oculto (`<!-- PLANE_WORKLOG_METADATA ... -->`) para telemetría analítica.
3. **Verdad Matemática Incontrovertible (Klee's Measure):** Las horas no se suman escalarmente. La unión matemática de intervalos de 1D garantiza que el tiempo reloj activo reportado sea estricto, mientras que el esfuerzo paralelo de subagentes se visibiliza en el **AI Leverage Multiplier**.
4. **Respeto a la Taxonomía N:M:** Los IDs de tickets pertenecen a los metadatos de Plane (`identifier`, `sequence_id`), las fases del SDLC pertenecen a los prefijos de título `[{FASE}]`, y los módulos funcionales pertenecen a las etiquetas indexadas de Plane (`sms`, `whatsapp`, `backend`), protegiendo el espacio útil de las tarjetas Kanban.

---

## 2. Nomenclatura y Metadatos: Aclaración Crucial sobre el Ticket ID

Existe una distinción vital entre la **base de datos de Plane**, las **ramas Git** y el **reporte plano para el jefe**:

| Entorno / Superficie | ¿Lleva el ID (ej. `OMNIFY-175`)? | Formato Canónico | Justificación Técnica |
| :--- | :---: | :--- | :--- |
| **Título en Plane (`name`)** | ❌ **NUNCA** | `[FEAT] Validaciones de esquema en campañas SMS` | Plane ya almacena el ID en columnas dedicadas (`identifier: OMNIFY`, `sequence_id: 175`) y lo renderiza automáticamente en la cabecera y en el badge de la tarjeta. Duplicarlo en el título come 12 caracteres innecesarios en el Kanban. |
| **Ramas Git** | ✔ **SÍ** | `feat/OMNIFY-175-campaign-form-validations` | En Git no hay metadatos nativos de Plane; el nombre de rama es el único enlace unívoco entre el commit y el issue tracker. |
| **Reporte Diario (Texto Plano)** | ✔ **SÍ** | `titulo: [OMNIFY-175] Validaciones de esquema en campañas SMS` | El reporte a jefatura se envía por WhatsApp o Email en texto plano; allí no existe la UI de Plane, por lo que el prefijo del ID es indispensable para saber de qué tarea se habla. |

---

## 3. Ciclo de Vida Operativo de Punta a Punta

### 3.1 Momento Cero (Zero-Moment Discovery con FTS5)
Al abrir una sesión de terminal en cualquier asistente (`agy`, `Claude Code`, `OpenCode`), el desarrollador expresa una intención en lenguaje natural:
```bash
# Ejemplo: "oye, arreglemos las validaciones del formulario de campaña"
plane-tracker search "validaciones formulario"
```
* **Tiempo de respuesta:** `< 0.08 segundos` (vía SQLite Virtual Table FTS5 con tokenizador `unicode61 remove_diacritics 2`).
* **Comportamiento:**
  - Si encuentra coincidencia: Muestra el ticket existente (ej. `OMNIFY-175`), su estado actual y sugiere hacer checkout a su rama.
  - Si no existe: Confirma que es un requerimiento nuevo y propone el comando de creación con título, prioridad y etiquetas sugeridas.

### 3.2 Creación Inteligente y Sugerencia de Ramas Git
Cuando se crea un ticket mediante el CLI:
```bash
plane-tracker create "[SPIKE] Auditoría de concurrencia en envíos masivos SMS" \
  --priority "high" \
  --labels "backend,sms,bug" \
  -d "Análisis forense de deadlocks..."
```
El motor de `plane.py`:
1. Identifica el prefijo `[SPIKE]`.
2. Asocia las etiquetas validadas contra la tabla local `labels`.
3. Deriva automáticamente la rama Git según la fase:
   - `[SPIKE]` o `[RFC]` ➔ `spike/OMNIFY-XXX-descripcion`
   - `[FIX]` ➔ `fix/OMNIFY-XXX-descripcion`
   - `[FEAT]` ➔ `feat/OMNIFY-XXX-descripcion`
   - `[INFRA]` ➔ `infra/OMNIFY-XXX-descripcion`
   - `[QA]` o `[TEST]` ➔ `test/OMNIFY-XXX-descripcion`
   - `[REFACTOR]` ➔ `refactor/OMNIFY-XXX-descripcion`

### 3.3 Living Ticket Pattern (Manejo de la Incertidumbre)
En bugs o incidentes, exigir soluciones o criterios de aceptación al inicio es inviable. Se aplica el **Patrón del Ticket Vivo en 3 Fases**:

```
[Alerta / Triage] ➔ ¿Toma < 15 min? ➔ SÍ ➔ Absorber en Ticket Paraguas de OPS
                                   ➔ NO ➔ Crear en Plane (Fase 1: Incertidumbre)
                                            │
                                            ▼
                                  [Causa Raíz Aislada] ➔ Actualizar Plane (Fase 2: RCA + Solución + DoD)
                                            │
                                            ▼
                                  [Construcción y QA] ➔ Cerrar Plane (Fase 3: DoD [x] + Bitácora Dual)
```

1. **Fase 1 (Incertidumbre Inicial):** Documenta únicamente:
   - *Contexto y Componente afectado.*
   - *Comportamiento Observado (Síntoma).*
   - *Comportamiento Esperado.*
   - *Evidencia de Muestra e Hipótesis.*
   - *Plan de Investigación (Spike Checklist).*
2. **Fase 2 (Causa Raíz Aislada):** Se actualiza la descripción en Plane inyectando:
   - *Causa Raíz Confirmada (RCA).*
   - *Solución Propuesta y Arquitectura.*
   - *Criterios de Aceptación Técnicos (DoD).*
3. **Fase 3 (Cierre Verificable):**
   - Checkboxes de DoD marcados `[x]`.
   - Entregables verificables (PRs, scripts de migración).
   - Publicación de la Bitácora Dual-Layer como comentario final.

### 3.4 Protocolo de Relevo Asíncrono (Task Handoff)
Permite que un ticket sea iniciado por Pierre, transferido a Johan y viceversa, sin pérdida de contexto ni contaminación de horas:

1. **Recepción del Relevo (Handoff Ingest):**
   - Al ejecutar `plane-tracker get <TICKET>`, el CLI descarga la descripción y los comentarios recientes.
   - El agente filtra el ruido y extrae:
     * *¿Qué intentó el colega anterior y qué funcionó?*
     * *¿Dónde se quedó la última prueba?*
     * *¿Cuáles son los stoppers y dependencias?*
     * *¿Cuál es el siguiente paso inmediato?*
2. **Aislamiento de Telemetría:**
   - Johan trabaja en su propia rama Git.
   - Johan imputa sus horas efectivas exclusivamente bajo su propio usuario y track mediante `plane-tracker comment`. Las horas de Pierre quedan asociadas a su usuario.
3. **Entrega del Relevo (Si se deja a medias):**
   - Si Johan debe suspender la tarea o devolverla a Pierre, publica un comentario estructurado de relevo (*Handoff Snapshot*):
     ```markdown
     ### 🔄 Relevo de Tarea (Handoff Snapshot)
     - **Avance realizado:** Qué se probó o diagnosticó en esta sesión.
     - **Rama Git / Commit:** `feat/OMNIFY-XXX-...` (commit `abcdef1` en remote).
     - **Estado actual:** Qué componentes están estables y probados.
     - **Stoppers / Próximo paso:** Qué le toca a la siguiente persona para continuar.
     ```

### 3.5 Tickets Paraguas Semanales (Umbrella Tickets)
Para no crear 20 micro-tickets a la semana que destruyan las métricas de sprint, se mantienen **dos tickets paraguas semanales recurrentes** (cadencia `W{ISO_WEEK}`):

1. **En `OPS` (Soporte y Toil):**  
   `Tareas Rápidas y Soporte - W{XX}`  
   *Balde:* `toil_support` | *Labels:* `externo`, `infra`.  
   *Uso:* Atender consultas de usuarios de Ripley, revisar un log en Caddy, reiniciar un worker.
2. **En `OPS` (Coordinación de Equipo):**  
   `Reuniones de Equipo y Acuerdos - W{XX}`  
   *Balde:* `coordination` | *Labels:* `docs`.  
   *Uso:* Daily meeting matutino, reuniones 1:1 con Pierre, balance de sprint.

---

## 4. Motor Matemático de Concurrencia y Telemetría

### 4.1 Fusión de Intervalos de Klee (Medida de Lebesgue en 1D)
Cuando múltiples sesiones o subagentes trabajan en paralelo sobre el mismo ticket o en tickets cruzados, la suma escalar de horas infla el tiempo por encima de la jornada real.

El algoritmo implementado en `plane.py` ordena todos los intervalos temporales $[s_i, e_i]$ y calcula su unión matemática continua:
$$\mu\left(\bigcup_{i=1}^n [s_i, e_i]\right)$$

* **Wall-Clock Time:** El tiempo real de reloj que Johan estuvo activo frente a la máquina.
* **Total Compute Effort:** La suma escalar del trabajo humano más el trabajo de los subagentes.
* **AI Leverage Multiplier:**
  $$\text{AI Leverage} = \frac{\text{Total Compute Effort}}{\text{Wall-Clock Time}}$$

### 4.2 Taxonomía Determinista de Pausas
1. **Pausas Invisibles (Almuerzo / Baño / Interrupción externa):**
   - Detección de **Idle Gap > 20 minutos** sin interacción.
   - El sistema corta el intervalo de trabajo al último evento real. Al retomar, inicia un nuevo bloque. No se computan horas falsas en el reporte del jefe.
2. **Pausas Pasivas (Build de Docker / Subagente background pesado):**
   - Se registran como `standby_reason = "Docker build"`.
   - No computan como foco cognitivo humano, pero sí computan en el esfuerzo de cómputo de la IA (apalancamiento).
3. **Stoppers Explícitos (Bloqueo externo de Meta / Esperando a Pierre):**
   - El ticket se mueve a `Pausado`.
   - Se reporta en el resumen diario como `⏸️ Standby externo: Meta API Webhook (2h 15m)`, justificando el Lead Time ante la gerencia.

---

## 5. Arquitectura de Datos Local (SQLite3 WAL en `worklogs.db`)

La base de datos local en `~/.cache/plane/worklogs.db` opera con `PRAGMA journal_mode = WAL;`, `busy_timeout = 10000;`, y `synchronous = NORMAL;`, garantizando concurrencia libre de bloqueos (*Zero-Lock Contention*).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ESQUEMA RELACIONAL SQLITE3                      │
├──────────────────┬──────────────────┬─────────────────┬────────────────┤
│ projects         │ labels           │ states          │ issues_cache   │
├──────────────────┼──────────────────┼─────────────────┼────────────────┤
│ identifier (PK)  │ id (PK)          │ id (PK)         │ id (PK)        │
│ project_id       │ project_id       │ project_id      │ sequence_id    │
│ name             │ name             │ name            │ ticket_id      │
│ workspace        │ color            │ slug            │ project_id     │
│ updated_at       │ updated_at       │ group_name      │ title          │
│                  │                  │ is_default      │ state_name     │
│                  │                  │ updated_at      │ state_group    │
│                  │                  │                 │ priority       │
│                  │                  │                 │ updated_at     │
├──────────────────┴──────────────────┴─────────────────┴────────────────┤
│ Virtual Table: issues_fts (FTS5 BM25 unicode61 remove_diacritics 2)    │
├────────────────────────────────────────────────────────────────────────┤
│ worklogs (Primary Key: ticket_id, track, date, start_time)             │
├────────────────────────────────────────────────────────────────────────┤
│ • duration_minutes • worker_type • capacity_bucket • phase • role     │
│ • notes • stoppers_json • raw_payload (Dual-Layer JSON)                │
└────────────────────────────────────────────────────────────────────────┘
```

**Tablas y archivos adicionales (misma base, `~/.cache/plane/`):**

| Elemento | Contenido | ¿Se reconstruye desde Plane? |
| :--- | :--- | :--- |
| `issues_cache` (+ `created_at`, `completed_at`, `start_date`, `target_date`, `archived_at`) | Estado y fechas del ciclo de vida de cada issue. | Sí (`search`/sync). |
| `state_transitions` + `flow_fetch` | Historial de estados (de `/issues/<id>/activities/`, una llamada por ticket) y control incremental por `updated_at`. | Sí. |
| `session_marks` | Marcas de `focus`: qué ticket trabaja cada sesión de agente. | **No** (solo local; los `segments` sí viajan en el comentario). |
| `last_proposal.json` (+ `.lock`) | Propuestas de duración y repartos pendientes (30 min), por ticket **y sesión**; escritura atómica con `flock`. | No (efímero). |
| `requests.log` (+ `.1`) | JSONL con método, ruta, estado, ms, intento y error de cada llamada a la API (sin cuerpos ni cabeceras); rota a 1 MB; lo resume `health`. | No (diagnóstico). |

**La telemetría viaja con el comentario.** Cada `comment` añade al HTML el bloque oculto `<!-- PLANE_WORKLOG_METADATA {json} -->` (Plane lo conserva) con fecha, horas, duración, track, capacidad, `segments[]` y `measured_by` (`proposal` | `proposal_split` | `declared`, sesión, adaptador, confianza, atribución, `window_override`). Así `report --sync` reconstruye `worklogs` aunque se pierda la caché. Comentarios anteriores a este cambio no traen el bloque.

**Medición por sesión de agente (`scripts/session_clock.py`).** Lee solo timestamps/ids de Claude Code (`~/.claude/projects`), OpenCode (`opencode.db`) y Antigravity CLI (`conversation_summaries.db`), nunca contenido. La sesión se resuelve por variable de entorno (`CLAUDE_CODE_SESSION_ID`), `--session`, o el directorio de trabajo si no hay ambigüedad; no se adivina entre varias. La actividad se mide en *tramos* (huecos > 10 min excluidos); de cada propuesta se restan los worklogs de la sesión (por su intervalo real) y las propuestas pendientes de otros tickets, de modo que nada se cuenta dos veces. Un día pasado se mide con `--date`.

**Flujo por ticket (`scripts/flow_metrics.py`).** Lead time (`created_at` → cierre), cycle time (tiempo en estados *started* sin *Pausado*), tiempo por estado y esfuerzo (reloj = unión de intervalos/segmentos; cómputo = suma). Flags internos en inglés: `no_transition`, `no_started`, `instant_close`, `umbrella`, `unknown_state`.

---

## 6. Especificación de Comandos del CLI `plane-tracker`

| Comando | Sintaxis | Descripción y Rendimiento |
| :--- | :--- | :--- |
| **`search`** | `plane-tracker search "validaciones"` | Búsqueda ultra-rápida FTS5 en Momento Cero (**< 80ms**). |
| **`create`** | `plane-tracker create "[FIX] Titulo" -p OMNIFY -d "..."` | Crea issue en Plane y autogenera rama Git según la fase. |
| **`get`** | `plane-tracker get OMNIFY-197` | Muestra metadata, descripción y **contexto de comentarios / handoff**. |
| **`update`** | `plane-tracker update OMNIFY-162 --state "Progreso"` | Actualiza estado, prioridad o etiquetas en Plane. |
| **`comment`**| `plane-tracker comment OMNIFY-162 -f worklog.md --track "main" --duration 95` | Publica bitácora dual-layer con telemetría v2.2. |
| **`labels`** | `plane-tracker labels [-p OMNIFY] [--refresh]` | Lista etiquetas indexadas desde caché local (**< 2ms**). |
| **`projects`**| `plane-tracker projects [--refresh]` | Lista proyectos dinámicos del workspace (`teamprogra`). |
| **`report`** | `plane-tracker report --today [--week] [--json]` | Genera reporte híbrido para jefatura con Klee's Merging (**< 0.1s**). |
| **`report --flow`** | `plane-tracker report --flow --week [-p OMNIFY] [--json]` | Flujo por ticket del periodo: lead/cycle time, tiempo por estado, esfuerzo y medianas. |
| **`get --history`** | `plane-tracker get OMNIFY-197 --history [--no-comments] [--last N] [--full]` | Ciclo de vida, estado, flujo y transiciones; flags para ahorrar tokens. |
| **`propose-duration`** | `plane-tracker propose-duration OMNIFY-197 [--split A=60%,B=rest] [--since H --until H] [--date D]` | Mide la sesión del agente y propone la duración (solo lectura). `comment --accept-proposal` la registra. |
| **`focus`** | `plane-tracker focus OMNIFY-197` · `--off` · `--status` | Marca en qué ticket trabaja la sesión para atribuir el tiempo medido por ticket. |
| **`comment-edit` / `comment-delete`** | `plane-tracker comment-edit T --comment-id ID [--duration N] [--embed-metadata]` | Edita/vincula un comentario con su worklog, o lo elimina junto con su worklog local. |
| **`link`** | `plane-tracker link OMNIFY-197 https://github.com/org/repo/pull/7 --title "PR #7"` | Adjunta un enlace al work item (idempotente). |
| **`attach` / `attachments`** | `plane-tracker attach T archivo... [--replace ID]` · `attachments T [--delete ID]` · `create ... --attach F` | Sube, lista, reemplaza y elimina adjuntos (50 MB máx.). |
| **`handoff`** | `plane-tracker handoff [TICKET] [--base dev]` | Borrador del Handoff Snapshot con hechos de git local (rama, SHA, repo, sin pushear → bloquea); no publica. `comment` rechaza `[COMPLETAR]`. |
| **`report --check`** | `plane-tracker report --check [--week] [--json]` | Solo lectura: duplicados, huérfanos y diferencias entre `worklogs` y los bloques ocultos de los comentarios. |
| **`health`** | `plane-tracker health [--hours 24]` | Latencia (p50/p95) y errores recientes de la API desde `requests.log`. |

---

## 7. Optimización de Tokens y Eficiencia DX

### ¿Por qué CLI Local vs MCP Server Pesado?
1. **Ahorro Masivo de Context Window (90% menos tokens):**  
   Un tool call de MCP inyecta esquemas JSON gigantescos en cada turno del LLM. Con `plane-tracker`, el asistente ejecuta un comando Bash determinista de 1 línea, consumiendo apenas 30-50 tokens.
2. **Independencia de Modelos:**  
   Funciona de manera idéntica en Gemini CLI (`agy`), Claude Code, OpenCode o en un script de bash propio de Johan sin IA.
3. **Convivencia Armónica con OMNIFY-197:**  
   Cuando se despliegue el MCP remoto de OMNIFY-197, será utilizado exclusivamente por `claude.ai` en web/móvil para gestión conversacional de producto. En la máquina de desarrollo de Johan, `plane-tracker` sigue siendo el motor de ingeniería local de alto rendimiento.

---
*Documento de arquitectura maestro consolidado y verificado en el entorno de producción de Johan Tanta.*
