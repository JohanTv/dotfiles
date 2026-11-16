# 🛠️ Guía Operativa del CLI `alo` (`alo ticket`)
## Manual de Comandos, Flags, Caché Local y Automatizaciones en Terminal

**Binario:** `~/.local/bin/alo`  
**Wrapper Dotfiles:** `Code/dotfiles/bin/common/alo`  
**Motor:** Motor nativo en Go de Allostasis (`alo`)  
**Caché Relacional:** SQLite local en modo WAL (gestión interna)

---

## 0. Setup inicial (primera vez)

Antes de ejecutar `alo`, verifica que las variables de entorno estén en `~/.zshrc.local`; si falta alguna, pídele los valores al usuario.

```bash
export PLANE_BASE_URL="https://plane.tudominio.com"   # URL base de la instancia, sin barra final
export PLANE_WORKSPACE="tu-workspace"                 # slug del workspace (visible en la URL)
export PLANE_API_KEY="tu-api-key"                     # Plane → Perfil → API Tokens
export PLANE_USERNAME="tu@email.com"                  # email o display_name: filtra tu reporte y no mezcla horas ajenas
# export PLANE_ACTOR_UUID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # opcional y más robusto; obtenlo con `alo ticket whoami`
```

Onboarding del agente (primera invocación o error de configuración):

1. Verifica con `alo ticket whoami 2>&1`.
2. Si falta una variable, pregunta la URL de la instancia, la API Key y el username o email en Plane.
3. Escribe los valores en `~/.zshrc.local` (`echo 'export VAR=...' >> ~/.zshrc.local`), recarga con `source ~/.zshrc.local` y verifica con `alo ticket whoami`.
4. Nunca expongas la API Key en logs, artefactos ni chat.

---

## 1. Resumen de Comandos Principales

```bash
# 1. Búsqueda en Momento Cero (caché local, título y etiquetas; incluye cerrados y cancelados)
alo ticket list --text "<términos de búsqueda>" --all-projects --limit 5 --brief --json

# 2. Creación de ticket con sugerencia automática de rama Git
alo ticket create "[FEAT] Título descriptivo" -p OMNIFY --priority high --labels "backend,sms"
# (rechaza un título repetido de las últimas 24 h: --allow-duplicate lo permite)

# 3. Consulta de detalles de ticket con notas de handoff y comentarios
alo ticket get <TICKET-ID>

# 4. Actualización de estado, prioridad, etiquetas o título
alo ticket update <TICKET-ID> --state "Progreso" --priority "urgent"

# 5. Publicación de bitácora corta (formato en SKILL.md §4; la CLI agrega la telemetría)
alo ticket comment add <TICKET-ID> -f /tmp/worklog.md --track "main" --duration 95

# 6. Inspección de taxonomía de etiquetas del proyecto (< 2ms)
alo ticket labels [-p OMNIFY]

# 7. Listado de proyectos disponibles en el workspace
alo projects

# 8. Generador de reportes de actividad con Interval Merging de Klee
alo report time
alo report time --week
```

### Convenciones de nombrado

* En la raíz viven los verbos del ticket (`get`, `list`, `create`, `update`), `handoff`, los catálogos en plural (`labels`, `projects`), los diagnósticos (`whoami`, `health`) y `report`.
* Toda otra familia es un grupo `<sustantivo singular> <verbo>`: `comment`, `attachment`, `link`, `outbox`, `focus`, `worklog`.
* Un flag nunca elige la operación: solo modifica el comportamiento o añade una sección (p. ej. `get --history`, `report time --refresh`).
* Verbos: `add` / `list` / `edit` / `delete` / `replace` / `flush`; marcas `set` / `clear` / `status`; derivados `propose` / `check`.
* El ID de un hijo que es obligatorio va posicional (`attachment delete ISSUE ID`); si es opcional (por defecto, tu último comentario) va como `--comment-id`.
* `--json` es global: funciona antes o después del comando.
* Un nombre antiguo, un sinónimo o un verbo faltante termina con exit 2 y un mensaje que indica el comando correcto, antes de validar el entorno.

---

## 2. Detalle de Comandos

### `alo ticket list` con filtros (mis tickets)
Vista filtrada desde la caché local; funciona sin conexión y avisa de la antigüedad de los datos. Necesita saber quién eres (`PLANE_ACTOR_UUID` o `PLANE_USERNAME`; `alo ticket whoami` lo comprueba).

```bash
alo ticket list --mine --open               # asignados a ti ahora (según la última sincronización), sin cerrados
alo ticket list --created --all-projects    # creados por ti, en todos los proyectos
alo ticket list --involved --open           # asignado, creador, con horas tuyas o asignado alguna vez, con la razón de cada uno
alo sync                                    # sincroniza eventos diferidos y actualiza outbox
```
*Qué NO afirma:* `--involved` muestra "Historial de asignación verificado en X de Y tickets": que un ticket no aparezca no prueba que nunca estuviste asignado. Las horas registradas salen solo de la base local de esta máquina. Detalle y límites en `docs/decisions/0019`.

### A. `alo ticket list --text` (Búsqueda Momento Cero)
Permite saber si un requerimiento ya existe en Plane antes de codificar o duplicar tickets. Búsqueda con `alo ticket search "<texto>"` o `alo ticket list --text`, que busca en **título y etiquetas**, ordena por relevancia y se combina con cualquier otro filtro. Responde desde la caché local.

```bash
# Búsqueda en todos los proyectos accesibles, 5 filas breves, para un agente
alo ticket list --text "validaciones formulario" --all-projects --limit 5 --brief --json

# Solo un proyecto (ej: Operaciones) y solo lo abierto
alo ticket list --text "soporte ripley" -p OPS --open

# Búsqueda tolerante directa
alo ticket search "caddy" -p OPS

# Salida estructurada
alo ticket search "mcp" --json
```

**Antes de concluir "no hay duplicado", lee `coverage`:** si `unavailable` no está vacío, `stale` es `true` o `complete` no es `true`, el resultado no prueba ausencia. Un identificador como texto (`OMNIFY-12`) no se busca como ticket: usa `alo ticket get OMNIFY-12` (con `--verbose` la nota `text_looks_like_id` lo recuerda).

---

### B. `alo ticket create` (Creación Estructurada)
Publica el issue en Plane, vincula las etiquetas locales, asigna el estado inicial y **genera la sugerencia de rama Git según la fase**.

```bash
# Creación estándar en Omnify
alo ticket create "[FEAT] Validaciones de formulario de campaña SMS" \
  --priority "high" \
  -d "Detalles del requerimiento..."

# Creación de un Spike de diagnóstico
alo ticket create "[SPIKE] Análisis de deadlock en tabla SEM-MKT" \
  --priority "urgent"

# Creación en otro proyecto con estado inicial específico
alo ticket create "Tareas Rápidas y Soporte - W44" \
  -p OPS \
  --state "Progreso" \
  --priority "medium"
```

#### Salida en Terminal:
```text
🎉 Ticket creado exitosamente: OMNIFY-202
   • Título: [FEAT] Validaciones de formulario de campaña SMS
   • Prioridad: HIGH
   • Enlace: https://plane.example.com/mi-workspace/projects/<uuid>/issues/...
   • Sugerencia de rama Git: feat/OMNIFY-202-validaciones-de-formulario-de-c
```

---

### C. `alo ticket get` (Contexto de Relevo y Comentarios)
Muestra la metadata, descripción del ticket y **extrae el historial cronológico de comentarios** para destilar el handoff.

```bash
# Consultar ticket existente
alo ticket get OMNIFY-197
alo ticket get OPS-44

# Salida JSON para procesamiento por LLM (incluye state_name)
alo ticket get OMNIFY-197 --json
```

---

### C.1 Foco de sesión (`alo ticket focus`) y Telemetría (`alo log`)
```bash
# Atribución por foco de sesión
alo ticket focus set OMNIFY-205        # abre la marca activa
alo ticket focus set OPS-13            # cambio de ticket
alo ticket focus status                # verifica el ticket activo
alo ticket focus clear                 # cierra la marca

# Registro de sesión en el ledger alostático
alo log OMNIFY-205 60 "Desarrollo de validaciones de esquema" --bucket deep_work
alo log OPS-13 40 "Soporte operativo a incidencias" --bucket toil_support
```
*Fuentes:* Claude Code (transcript, `$CLAUDE_CODE_SESSION_ID`), OpenCode (`opencode.db`, solo `time_created`), Antigravity CLI (`conversation_summaries.db`, solo hitos; confianza baja). Las pausas de más de 10 min se descuentan de la medición neta.

---

### C.2 Flujo del work item: tiempo abierto vs esfuerzo efectivo
```bash
alo ticket get OMNIFY-129 --history            # lead/cycle time, tiempo por estado, esfuerzo y transiciones
alo ticket get OMNIFY-129 --include attachments,links   # adjuntos y enlaces (+1 GET cada uno; sin el flag no se leen)
alo ticket get OMNIFY-129 --all                # todo lo incluible hoy (attachments y links); relations y children avisan: aún no implementados
alo report flow --week [-p OMNIFY]      # tabla por ticket del periodo + medianas (con --offline, sobre lo almacenado)
```
- **Lead time** = `created_at` → cierre (`completed_at`; en cancelados, la transición a Cancelado). Abiertos: hasta hoy.
- **Cycle time** = suma del tiempo en estados del grupo *started* (Progreso, Revisión, Pruebas); **Pausado se excluye del activo** y se muestra en el bruto. Reaperturas suman cada tramo.
- **Esfuerzo**: *reloj* = unión de intervalos de los worklogs (sin doble conteo) y *cómputo* = suma de `duration_minutes` (puede superar al reloj con agentes en paralelo). Fuente: worklogs locales ∪ metadata en comentarios de Plane.
- **Flags** (internal identifiers, English): `no_transition` (no state history), `no_started` (never entered a *started* state), `instant_close` (closed in under 5 min: bulk close or backfill), `umbrella` (weekly umbrella ticket `- W{NN}`), `unknown_state` (a state id missing from the project's states). Medians of lead time exclude `umbrella`, `instant_close` and `no_transition`; cycle medians skip `no_started`; `unknown_state` only warns. All times are calendar; lead/cycle in UTC, worklogs converted from local time.
- Las transiciones salen de `/issues/<id>/activities/` (una llamada por ticket, cacheada en `state_transitions`; los cerrados no se vuelven a pedir si su `updated_at` no cambió).

---

> **Telemetry travels with the comment:** `comment add` always appends the hidden `<!-- PLANE_WORKLOG_METADATA {...} -->` block to the HTML (Plane preserves it, verified), so hours survive losing the local cache and can be rebuilt with `report --refresh`. Comments published before this change have no block.

---

### C.3 `alo ticket link add` y `comment edit --embed-metadata`
```bash
alo ticket link add OMNIFY-205 https://github.com/org/repo/pull/23 --title "PR #23"   # panel de enlaces del work item (idempotente)
alo ticket comment edit OMNIFY-205 --comment-id <uuid> --embed-metadata           # añade el bloque oculto de un comentario previo
alo ticket comment edit OMNIFY-205 --comment-id <uuid> --duration 45 [--track T --capacity C]   # CORRIGE un worklog: reemplaza el bloque oculto y la fila local a la vez
alo ticket comment edit OMNIFY-205 --comment-id <uuid> --since 14:40 --until 18:20 [--date D]   # CORRIGE la ventana real: la duración pasa a ser la del intervalo
alo ticket comment edit OMNIFY-205 --comment-id <uuid> -m "nuevo texto"                         # edita el texto conservando la telemetría
alo ticket comment delete OMNIFY-205 --comment-id <uuid>                                         # elimina comentario + worklog local
alo ticket delete OMNIFY-205 [--yes] [--discard-worklogs]                                         # elimina el ticket (irreversible); sin --yes solo muestra el alcance; con horas propias exige --discard-worklogs; con horas de otros se niega (ver docs 0018)
```
*Corregir un tiempo mal registrado:* nunca se edita solo la fila local, porque `report time --refresh` la reescribiría desde el bloque oculto del comentario. `comment edit --duration` parte del bloque existente (conserva sesión, fechas y tramos), cambia solo lo pedido, marca `measured_by.kind="corrected"` (con el tipo original en `was`), guarda `previous_duration_minutes` y `edited_at`, y actualiza bloque y fila juntos. **Para cambiar inicio y fin usa `--since/--until`** (con `--date` si el trabajo fue otro día): con los dos extremos la duración es la del intervalo; con uno solo se completa con `--duration` o con la duración ya registrada. Si el worklog tiene tramos medidos que no suman la nueva duración, pide `--force` (descarta los tramos; el rango inicio–fin sigue cubriendo la sesión para no recontarla).

Prefiere `link add` para PRs y documentos (queda estructurado y no notifica como comentario); el comentario de relevo sigue siendo para contexto y tiempo.

---

### C.4 Adjuntos y salud de la conexión
```bash
alo ticket attachment add OMNIFY-205 informe.pdf captura.png   # sube archivos (máx. 50 MB c/u); si falla no deja adjuntos huérfanos
alo ticket attachment list OMNIFY-205 [--json]                 # lista los adjuntos (con su id)
alo ticket attachment delete OMNIFY-205 <id>                   # elimina un adjunto
alo ticket attachment replace OMNIFY-205 <id> nuevo.pdf        # "actualizar": sube el nuevo y, si salió bien, borra el anterior
alo ticket create "[FEAT] ..." --attach spec.pdf               # adjuntar al crear (se sube justo después; el ticket ya existe si falla)
alo health [--hours 24] [--json]                        # latencia (p50/p95) y errores recientes de la API
```
Plane no permite editar un adjunto (solo confirmar su subida) ni subirlo en la propia creación del ticket: ambos son pasos aparte. Flujo de Plane: crear adjunto → POST firmado al almacenamiento → confirmar `is_uploaded`. Cada llamada a la API deja un registro interno para diagnosticar y distinguir caídas de lentitud mediante telemetría.

---

### C.5 Relevo y consistencia
```bash
alo handoff [TICKET] [--base dev]   # borrador del Handoff Snapshot con hechos de git (no publica); ver PROTOCOLO_RELEVO §6
alo worklog check [--week | --from D [--to D]] [-p OMNIFY] [--json]   # solo lectura: compara worklogs locales con sus comentarios
```
`worklog check` informa por ticket: `duplicate` (varias filas para un comentario), `orphan` (el comentario ya no existe), `mismatch` (fecha, horas, duración, track, capacidad o tipo distintos entre fila y bloque), `missing_local` (comentario con telemetría sin fila local: usa `report --refresh`) y, como aviso, `no_block` (comentario sin telemetría, no reconstruible), `pending` (fila en cola de publicación) y `unlinked`. Sale con código 1 si hay inconsistencias.

---

### C.6 Plane caído: `outbox`
Exit 3 significa que Plane no responde (circuito abierto, timeouts o `PLANE_OFFLINE=1`). Las lecturas responden con lo local y avisan su antigüedad; `alo log` registra localmente y encola para posterior entrega; el resto de las escrituras falla con exit 3.
```bash
alo outbox list [--all] [--json]                         # registros abiertos con vista previa (nunca el texto completo)
alo sync [--limit N]                                     # procesa outbox y publica en orden de creación
alo outbox drop ID [--force] [--keep-worklog] [--json]   # descarta un registro y su worklog provisional
```
`sync` sondea Plane aunque el circuito esté en enfriamiento, se detiene ante el primer fallo de disponibilidad (exit 3), marca `failed` los rechazados (404, 400...) y sigue.

---

### D. `alo ticket update` (Transiciones de Estado y Renombrado)
Permite mover tickets entre columnas del Kanban y corregir su título sin abrir el navegador.

```bash
# Mover a Progreso
alo ticket update OMNIFY-175 --state "Progreso"

# Renombrar el ticket (útil al cambiar de fase, ej. RFC → FEAT)
alo ticket update OMNIFY-175 --title "[FEAT] Validaciones de formulario en campañas SMS"

# Mover a Pruebas y cambiar prioridad
alo ticket update OMNIFY-175 --state "Pruebas" --priority "high"

# Pausar por bloqueo externo
alo ticket update OMNIFY-175 --state "Pausado"

# Marcar como Completado
alo ticket update OMNIFY-175 --state "Completado"
```
*Estados válidos:* `Backlog`, `Pendiente`, `Progreso`, `Pruebas`, `Revisión`, `Completado`, `Pausado`, `Cancelado`.

---

### E. `alo log` / `alo ticket comment add` (Bitácora Dual-Layer)
Registra la sesión y esfuerzo mediante `alo log`, o publica comentarios en el ticket:

```bash
# Registrar sesión mediante alo log
alo log OMNIFY-162 95 "Reconciliación de reportería SMS." --bucket deep_work

# Soporte operativo en ticket paraguas
alo log OPS-44 35 "Atención a comercial sobre campaña #842." --bucket toil_support

# Publicar comentario directo en ticket (si se requiere)
alo ticket comment add OMNIFY-162 -f /tmp/worklog.md --duration 95
```

---

### F. `alo report time` (Reporte Ejecutivo para Jefatura)
Genera el consolidado diario o semanal utilizando la **Unión de Intervalos de Klee** para evitar duplicar horas en paralelo.

```bash
# Reporte del día actual (formato para la jefatura a las 6:00 pm)
alo report time

# Reporte semanal (balance de sprint los viernes)
alo report time --week

# Filtrar por proyecto específico
alo report time -p OMNIFY

# Forzar sincronización remota previa
alo report time --refresh

# Vista de flujo (lead/cycle time y esfuerzo por ticket; no sincroniza, ignora --refresh)
alo report flow --week

# Salida en JSON para paneles o visualizaciones
alo report time --json
```

---

### G. `alo ticket labels` y `projects`
Inspección ultra-rápida de taxonomía viva desde SQLite.

```bash
# Listar etiquetas de Omnify (< 2ms)
alo ticket labels

# Listar etiquetas de Operaciones
alo ticket labels -p OPS

# Listar proyectos cacheados en el workspace
alo projects
```

---

## 9. Orquestación Multi-Repo (`alo ws`)

La orquestación de worktrees multi-repo, auditoría de merges (`git merge-tree`) y poda segura con respaldos automáticos se gestiona mediante el subcomando integrado `alo ws`. Consulte su [guía operativa dedicada](file:///home/johantv/Code/dotfiles/agents/skills/work/alo/references/GUIA_OPERATIVA_WORKTREES.md).
