# 🛠️ Guía Operativa del CLI `plane-tracker`
## Manual de Comandos, Flags, Caché Local y Automatizaciones en Terminal

**Binario:** `~/.local/bin/plane-tracker`  
**Wrapper Dotfiles:** `Code/dotfiles/bin/common/plane-tracker`  
**Motor Python:** `Code/dotfiles/agents/skills/work/plane-tracker/scripts/plane.py`  
**Caché Relacional:** `~/.cache/plane/worklogs.db` (SQLite3 WAL Mode)

---

## 1. Resumen de Comandos Principales

```bash
# 1. Búsqueda instantánea FTS5 en Momento Cero (< 2ms)
plane-tracker search "<términos de búsqueda>"

# 2. Creación de ticket con sugerencia automática de rama Git
plane-tracker create "[FEAT] Título descriptivo" -p OMNIFY --priority high --labels "backend,sms"

# 3. Consulta de detalles de ticket con notas de handoff y comentarios
plane-tracker get <TICKET-ID>

# 4. Actualización de estado, prioridad o etiquetas
plane-tracker update <TICKET-ID> --state "Progreso" --priority "urgent"

# 5. Publicación de bitácora dual-layer (humano + telemetría v2.2)
plane-tracker comment <TICKET-ID> -f /tmp/worklog.md --track "main" --duration 95

# 6. Inspección de taxonomía de etiquetas del proyecto (< 2ms)
plane-tracker labels [-p OMNIFY]

# 7. Listado de proyectos disponibles en el workspace
plane-tracker projects

# 8. Generador de reportes de actividad con Interval Merging de Klee
plane-tracker report --today
plane-tracker report --week
```

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

# Salida JSON para procesamiento por LLM
plane-tracker get OMNIFY-197 --json
```

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

### E. `plane-tracker comment` (Bitácora Dual-Layer)
Publica la bitácora de la sesión en el ticket y persiste el registro en SQLite local para los reportes diarios.

> ⚠️ **`--duration <minutos>` es obligatorio** si el contenido no incluye el bloque `PLANE_WORKLOG_METADATA` (donde puede ir como `duration_minutes` o `duration_net_minutes`). Sin esa fuente de duración el CLI **aborta antes de publicar**: la duración ya no se infiere ni se inventa. Si el hecho ocurrió fuera de la conversación del agente, pregúntale a Johan cuánto demoró antes de comentar.

```bash
# Publicar archivo de bitácora
plane-tracker comment OMNIFY-162 -f /tmp/worklog.md --duration 95

# Con track y tipo de trabajador especificado
plane-tracker comment OMNIFY-162 -f /tmp/worklog.md --track "form-validations" --worker-type "subagent" --duration 45

# Comentario rápido con mensaje en línea (ticket paraguas de OPS)
plane-tracker comment OPS-44 --track "soporte-ripley" --capacity "toil_support" --duration 35 -m "Atención a comercial sobre campaña #842."
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
plane-tracker report --today --sync

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
