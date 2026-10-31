# 🛠️ Guía Operativa del CLI `plane-tracker`
## Manual de Comandos, Flags, Caché Local y Automatizaciones en Terminal

**Binario:** `~/.local/bin/plane-tracker`  
**Wrapper Dotfiles:** `Code/dotfiles/bin/common/plane-tracker`  
**Motor Python:** `Code/dotfiles/agents/skills/work/plane-tracker/scripts/plane.py` (punto de entrada; el código está en `scripts/plane_cli/`)  
**Caché Relacional:** `~/.cache/plane/worklogs.db` (SQLite3 WAL Mode)

---

## 1. Resumen de Comandos Principales

```bash
# 1. Búsqueda instantánea FTS5 en Momento Cero (< 2ms)
plane-tracker search "<términos de búsqueda>"

# 2. Creación de ticket con sugerencia automática de rama Git
plane-tracker create "[FEAT] Título descriptivo" -p OMNIFY --priority high --labels "backend,sms"
# (rechaza un título repetido de las últimas 24 h: --allow-duplicate lo permite)

# 3. Consulta de detalles de ticket con notas de handoff y comentarios
plane-tracker get <TICKET-ID>

# 4. Actualización de estado, prioridad o etiquetas
plane-tracker update <TICKET-ID> --state "Progreso" --priority "urgent"

# 5. Publicación de bitácora dual-layer (humano + telemetría v2.2)
plane-tracker comment add <TICKET-ID> -f /tmp/worklog.md --track "main" --duration 95

# 6. Inspección de taxonomía de etiquetas del proyecto (< 2ms)
plane-tracker labels [-p OMNIFY]

# 7. Listado de proyectos disponibles en el workspace
plane-tracker projects

# 8. Generador de reportes de actividad con Interval Merging de Klee
plane-tracker report --today
plane-tracker report --week
```

### Convenciones de nombrado

* En la raíz viven los verbos del ticket (`search`, `get`, `list`, `create`, `update`), `handoff`, los catálogos en plural (`labels`, `projects`), los diagnósticos (`whoami`, `health`) y `report`.
* Toda otra familia es un grupo `<sustantivo singular> <verbo>`: `comment`, `attachment`, `link`, `outbox`, `focus`, `worklog`.
* Un flag nunca elige la operación: solo modifica el comportamiento o añade una sección (p. ej. `get --history`, `report --refresh`).
* Verbos: `add` / `list` / `edit` / `delete` / `replace` / `flush`; marcas `set` / `clear` / `status`; derivados `propose` / `check`.
* El ID de un hijo que es obligatorio va posicional (`attachment delete ISSUE ID`); si es opcional (por defecto, tu último comentario) va como `--comment-id`.
* `--json` es global: funciona antes o después del comando.
* Un nombre antiguo, un sinónimo o un verbo faltante termina con exit 2 y un mensaje que indica el comando correcto, antes de validar el entorno.

---

## 2. Detalle de Comandos

### A. `plane-tracker search` (Búsqueda Momento Cero)
Permite saber en **menos de 0.08 segundos** si un requerimiento ya existe en Plane antes de codificar o duplicar tickets.

```bash
# Búsqueda en el proyecto por defecto (OMNIFY)
plane-tracker search "validaciones formulario"
plane-tracker search "webhook sms"

# Búsqueda en otro proyecto (ej: Operaciones)
plane-tracker search "soporte ripley" -p OPS

# Forzar refresco desde Plane API si se crearon tickets muy recientemente
plane-tracker search "caddy" --refresh

# Salida estructurada en JSON para agentes de IA
plane-tracker search "mcp" --json
```

---

### B. `plane-tracker create` (Creación Estructurada)
Publica el issue en Plane, vincula las etiquetas locales, asigna el estado inicial y **genera la sugerencia de rama Git según la fase**.

```bash
# Creación estándar en Omnify
plane-tracker create "[FEAT] Validaciones de formulario de campaña SMS" \
  --priority "high" \
  --labels "frontend,sms,bug" \
  -d "Detalles del requerimiento..."

# Creación de un Spike de diagnóstico
plane-tracker create "[SPIKE] Análisis de deadlock en tabla SEM-MKT" \
  --priority "urgent" \
  --labels "backend,bd"

# Creación en otro proyecto con estado inicial específico
plane-tracker create "Tareas Rápidas y Soporte - W44" \
  -p OPS \
  --state "Progreso" \
  --priority "medium" \
  --labels "externo,infra"
```

#### Salida en Terminal:
```text
🎉 Ticket creado exitosamente: OMNIFY-202
   • Título: [FEAT] Validaciones de formulario de campaña SMS
   • Prioridad: HIGH
   • Enlace: http://190.105.240.58/teamprogra/projects/58371da4.../issues/...
   • Sugerencia de rama Git: feat/OMNIFY-202-validaciones-de-formulario-de-c
```

---

### C. `plane-tracker get` (Contexto de Relevo y Comentarios)
Muestra la metadata, descripción del ticket y **extrae el historial cronológico de comentarios** para destilar el handoff.

```bash
# Consultar ticket existente
plane-tracker get OMNIFY-197
plane-tracker get OPS-44

# Salida JSON para procesamiento por LLM (incluye state_name)
plane-tracker get OMNIFY-197 --json

# Control de tokens (por defecto se traen todos los comentarios, truncados a 300 caracteres)
plane-tracker get OMNIFY-197 --no-comments --no-description  # solo metadata y estado
plane-tracker get OMNIFY-197 --last 2                        # últimos 2 comentarios
plane-tracker get OMNIFY-197 --full                          # sin truncar descripción ni comentarios
```

---

### C.1b Varios tickets en una misma sesión
```bash
# Atribución automática por foco: avisa en qué ticket trabajas al cambiar de uno a otro
plane-tracker focus set OMNIFY-205        # abre la marca (cierra la anterior)
plane-tracker focus set OPS-13            # cambio de ticket
plane-tracker focus status                # minutos atribuidos hoy por ticket y tiempo sin foco
plane-tracker focus clear
plane-tracker worklog propose OMNIFY-205  # solo cuenta los intervalos con foco en ese ticket

# Reparto manual de lo medido (en un paso; cada parte se registra luego con su texto)
plane-tracker worklog propose --split OMNIFY-205=60%,OPS-13=rest   # o 40m; suma exacta (mayor resto)
plane-tracker comment add OMNIFY-205 -m "..." --accept-proposal
plane-tracker comment add OPS-13 -m "..." --accept-proposal             # en cualquier orden

# Ventana explícita (un solo día local; lo ya registrado de la sesión se excluye)
plane-tracker worklog propose OMNIFY-205 --since 09:30 --until 11:00

# Sesión de un día anterior (p. ej. el id que mostró Ctrl+C al cerrarla; `find-session -r -j` también lista ids)
plane-tracker worklog propose OMNIFY-205 --agent opencode --session ses_xxxx --date 2026-10-28
plane-tracker comment add OMNIFY-205 -m "..." --agent opencode --session ses_xxxx --accept-proposal
```
- La medición usa **tramos de actividad** (huecos de más de 10 min excluidos). Un worklog medido guarda `segments` (los tramos reales) para que el reloj por ticket y el reporte diario no usen un rango envolvente que pise a otro ticket.
- **Nada se cuenta dos veces:** de cada propuesta se restan los worklogs de la sesión (medidos o declarados, por su intervalo real) y las propuestas pendientes de otros tickets. Con foco activo, un ticket sin marcas hoy no recibe propuesta (usa `--duration`). Las marcas son locales (no se reconstruyen con `report --refresh`); los segmentos sí viajan en el bloque oculto del comentario.
- **Varias terminales o agentes:** cada propuesta pendiente pertenece a su sesión (`--accept-proposal` usa la de tu terminal y no adivina si hay varias). Claude Code resuelve su sesión solo (`$CLAUDE_CODE_SESSION_ID`); con OpenCode/agy, si hay más de una sesión reciente en el mismo directorio, indica `--session`. El tiempo en paralelo suma en *cómputo* y se une en *reloj* (AI Leverage).
- `measured_by` distingue `proposal`, `proposal_split` y `declared`, con `attribution` (`session`, `focus`, `split`) y `window_override` si se usó `--since/--until`.

---

### C.1 `plane-tracker worklog propose` (Duración medida)
Mide la sesión del agente (solo timestamps, nunca contenido) y propone una duración sin registrar nada.

```bash
plane-tracker worklog propose OMNIFY-197 --worker-type agent:claude
plane-tracker worklog propose OMNIFY-197 --agent opencode --session ses_xxxxxxxx   # sesión ambigua en el directorio
plane-tracker comment add OMNIFY-197 -m "..." --accept-proposal                         # registra lo propuesto (30 min, un solo uso)
```
*Fuentes:* Claude Code (transcript, `$CLAUDE_CODE_SESSION_ID`), OpenCode (`opencode.db`, solo `time_created`), Antigravity CLI (`conversation_summaries.db`, solo hitos; confianza baja). Las pausas de más de 10 min se descuentan de la medición neta.

---

### C.2 Flujo del work item: tiempo abierto vs esfuerzo efectivo
```bash
plane-tracker get OMNIFY-129 --history            # lead/cycle time, tiempo por estado, esfuerzo y transiciones
plane-tracker report flow --week [-p OMNIFY]      # tabla por ticket del periodo + medianas
```
- **Lead time** = `created_at` → cierre (`completed_at`; en cancelados, la transición a Cancelado). Abiertos: hasta hoy.
- **Cycle time** = suma del tiempo en estados del grupo *started* (Progreso, Revisión, Pruebas); **Pausado se excluye del activo** y se muestra en el bruto. Reaperturas suman cada tramo.
- **Esfuerzo**: *reloj* = unión de intervalos de los worklogs (sin doble conteo) y *cómputo* = suma de `duration_minutes` (puede superar al reloj con agentes en paralelo). Fuente: worklogs locales ∪ metadata en comentarios de Plane.
- **Flags** (internal identifiers, English): `no_transition` (no state history), `no_started` (never entered a *started* state), `instant_close` (closed in under 5 min: bulk close or backfill), `umbrella` (weekly umbrella ticket `- W{NN}`), `unknown_state` (a state id missing from the project's states). Medians of lead time exclude `umbrella`, `instant_close` and `no_transition`; cycle medians skip `no_started`; `unknown_state` only warns. All times are calendar; lead/cycle in UTC, worklogs converted from local time.
- Las transiciones salen de `/issues/<id>/activities/` (una llamada por ticket, cacheada en `state_transitions`; los cerrados no se vuelven a pedir si su `updated_at` no cambió).

---

> **Telemetry travels with the comment:** `comment add` always appends the hidden `<!-- PLANE_WORKLOG_METADATA {...} -->` block to the HTML (Plane preserves it, verified), so hours survive losing the local cache and can be rebuilt with `report --refresh`. Comments published before this change have no block.

---

### C.3 `plane-tracker link add` y `comment edit --embed-metadata`
```bash
plane-tracker link add OMNIFY-205 https://github.com/org/repo/pull/23 --title "PR #23"   # panel de enlaces del work item (idempotente)
plane-tracker comment edit OMNIFY-205 --comment-id <uuid> --embed-metadata           # añade el bloque oculto de un comentario previo
plane-tracker comment edit OMNIFY-205 --comment-id <uuid> --duration 45 [--track T --capacity C]   # CORRIGE un worklog: reemplaza el bloque oculto y la fila local a la vez
plane-tracker comment edit OMNIFY-205 --comment-id <uuid> -m "nuevo texto"                         # edita el texto conservando la telemetría
plane-tracker comment delete OMNIFY-205 --comment-id <uuid>                                         # elimina comentario + worklog local
```
*Corregir un tiempo mal registrado:* nunca se edita solo la fila local, porque `report --refresh` la reescribiría desde el bloque oculto del comentario. `comment edit --duration` parte del bloque existente (conserva sesión, fechas y tramos), cambia solo lo pedido, marca `measured_by.kind="corrected"` (con el tipo original en `was`), guarda `previous_duration_minutes` y `edited_at`, y actualiza bloque y fila juntos. Si el worklog tiene tramos medidos que no suman la nueva duración, pide `--force` (descarta los tramos; el rango inicio–fin sigue cubriendo la sesión para no recontarla).

Prefiere `link add` para PRs y documentos (queda estructurado y no notifica como comentario); el comentario de relevo sigue siendo para contexto y tiempo.

---

### C.4 Adjuntos y salud de la conexión
```bash
plane-tracker attachment add OMNIFY-205 informe.pdf captura.png   # sube archivos (máx. 50 MB c/u); si falla no deja adjuntos huérfanos
plane-tracker attachment list OMNIFY-205 [--json]                 # lista los adjuntos (con su id)
plane-tracker attachment delete OMNIFY-205 <id>                   # elimina un adjunto
plane-tracker attachment replace OMNIFY-205 <id> nuevo.pdf        # "actualizar": sube el nuevo y, si salió bien, borra el anterior
plane-tracker create "[FEAT] ..." --attach spec.pdf               # adjuntar al crear (se sube justo después; el ticket ya existe si falla)
plane-tracker health [--hours 24] [--json]                        # latencia (p50/p95) y errores recientes de la API
```
Plane no permite editar un adjunto (solo confirmar su subida) ni subirlo en la propia creación del ticket: ambos son pasos aparte. Flujo de Plane: crear adjunto → POST firmado al almacenamiento → confirmar `is_uploaded`. Cada llamada a la API deja un registro JSONL (sin cuerpos ni cabeceras) en `~/.cache/plane/requests.log` (rota a 1 MB) con método, ruta, estado, milisegundos, intento y error; `health` lo resume para distinguir caídas de lentitud.

---

### C.5 Relevo y consistencia
```bash
plane-tracker handoff [TICKET] [--base dev]   # borrador del Handoff Snapshot con hechos de git (no publica); ver PROTOCOLO_RELEVO §6
plane-tracker worklog check [--today|--week|--date D] [-p OMNIFY] [--json]   # solo lectura: compara worklogs locales con sus comentarios
```
`worklog check` informa por ticket: `duplicate` (varias filas para un comentario), `orphan` (el comentario ya no existe), `mismatch` (fecha, horas, duración, track, capacidad o tipo distintos entre fila y bloque), `missing_local` (comentario con telemetría sin fila local: usa `report --refresh`) y, como aviso, `no_block` (comentario sin telemetría, no reconstruible), `pending` (fila en cola de publicación) y `unlinked`. Sale con código 1 si hay inconsistencias.

---

### C.6 Plane caído: `outbox`
Exit 3 significa que Plane no responde (circuito abierto, timeouts o `PLANE_OFFLINE=1`). Las lecturas responden con lo local y avisan su antigüedad; `comment add` guarda el comentario con su worklog y lo encola (exit 0, `⏳ En cola`); el resto de las escrituras falla con exit 3.
```bash
plane-tracker outbox list [--all] [--json]                         # registros abiertos con vista previa (nunca el texto completo)
plane-tracker outbox flush [--limit N] [--include-old] [--retry-failed] [--json]   # publica en orden de creación
plane-tracker outbox drop ID [--force] [--keep-worklog] [--json]   # descarta un registro y su worklog provisional
```
`flush` sondea Plane aunque el circuito esté en enfriamiento, se detiene ante el primer fallo de disponibilidad (exit 3), marca `failed` los rechazados (404, 400...) y sigue, y omite los de más de 7 días salvo `--include-old`. Un registro cuya entrega es dudosa se busca en Plane por su `client_id` antes de reenviarse; `drop` de uno así exige `--force`. Mientras haya registros sin publicar, cada comando lo avisa por stderr. `PLANE_NO_QUEUE=1` hace que `comment add` falle con exit 3 en lugar de encolar.

---

### D. `plane-tracker update` (Transiciones de Estado)
Permite mover tickets entre columnas del Kanban sin abrir el navegador.

```bash
# Mover a Progreso
plane-tracker update OMNIFY-175 --state "Progreso"

# Mover a Pruebas y cambiar prioridad
plane-tracker update OMNIFY-175 --state "Pruebas" --priority "high"

# Pausar por bloqueo externo
plane-tracker update OMNIFY-175 --state "Pausado"

# Marcar como Completado
plane-tracker update OMNIFY-175 --state "Completado"
```
*Estados válidos:* `Backlog`, `Pendiente`, `Progreso`, `Pruebas`, `Revisión`, `Completado`, `Pausado`, `Cancelado`.

---

### E. `plane-tracker comment add` (Bitácora Dual-Layer)
Publica la bitácora de la sesión en el ticket y persiste el registro en SQLite local para los reportes diarios.

> ⚠️ **`--duration <minutos>` es obligatorio** si el contenido no incluye el bloque `PLANE_WORKLOG_METADATA` (donde puede ir como `duration_minutes` o `duration_net_minutes`). Sin esa fuente de duración el CLI **aborta antes de publicar**: la duración ya no se infiere ni se inventa. Si el hecho ocurrió fuera de la conversación del agente, pregúntale a Johan cuánto demoró antes de comentar.

```bash
# Publicar archivo de bitácora
plane-tracker comment add OMNIFY-162 -f /tmp/worklog.md --duration 95

# Con track y tipo de trabajador especificado
plane-tracker comment add OMNIFY-162 -f /tmp/worklog.md --track "form-validations" --worker-type "subagent" --duration 45

# Comentario rápido con mensaje en línea (ticket paraguas de OPS)
plane-tracker comment add OPS-44 --track "soporte-ripley" --capacity "toil_support" --duration 35 -m "Atención a comercial sobre campaña #842."
```

---

### F. `plane-tracker report` (Reporte Ejecutivo para Jefatura)
Genera el consolidado diario o semanal utilizando la **Unión de Intervalos de Klee** para evitar duplicar horas en paralelo.

```bash
# Reporte del día actual (formato para Pierre a las 6:00 pm)
plane-tracker report --today

# Reporte semanal (balance de sprint los viernes)
plane-tracker report --week

# Filtrar por proyecto específico
plane-tracker report --today -p OMNIFY

# Forzar sincronización remota previa
plane-tracker report --today --refresh

# Vista de flujo (lead/cycle time y esfuerzo por ticket; no sincroniza, ignora --refresh)
plane-tracker report flow --week

# Salida en JSON para paneles o visualizaciones
plane-tracker report --today --json
```

---

### G. `plane-tracker labels` y `projects`
Inspección ultra-rápida de taxonomía viva desde SQLite.

```bash
# Listar etiquetas de Omnify (< 2ms)
plane-tracker labels

# Listar etiquetas de Operaciones
plane-tracker labels -p OPS

# Forzar refresco si se crearon etiquetas en la web
plane-tracker labels --refresh

# Listar proyectos cacheados en el workspace
plane-tracker projects
```
