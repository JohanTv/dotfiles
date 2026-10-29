---
name: plane-tracker
description: Orquestador y registrador de tareas, estados, prioridades, etiquetas y bitácoras en Plane CE v1.2.3 bajo el patrón dual-layer (humano + telemetría analítica v2.1). Úsalo al iniciar tareas, al pasar a Pruebas/Revisión de PR, al cerrar sesiones o al finalizar hitos de desarrollo, research, tooling o deuda técnica.
---

# Plane Session Tracker & Worklog Operator (v2.1)

Procedimiento operativo integral para interactuar con la plataforma Plane CE v1.2.3 auto-hospedada de la empresa (Omnify / Operaciones) y alimentar el motor de telemetría y dashboard personal de `Code/plane-tracker`.

---

## 1. Mapeo Determinista de Estados y Ciclo de Vida del Ticket

Plane cuenta con estados oficiales por proyecto. Las transiciones de estado deben ser deterministas según el hito técnico alcanzado:

| Estado en Plane | Trigger Técnico del Asistente | Comando CLI |
| :--- | :--- | :--- |
| **`Pendiente`** | Tarea asignada en el sprint pero aún no comenzada. | `plane.py update OMNIFY-XXX --state Pendiente` |
| **`Progreso`** | Johan inicia actividades de Auditoría, Spike, RFC, Tooling o Desarrollo activo. | `plane.py update OMNIFY-XXX --state Progreso` |
| **`Pruebas`** | Código/script listo; ejecutando dry-run transaccional, test suite o réplica. | `plane.py update OMNIFY-XXX --state Pruebas` |
| **`Revisión`** | **PR subido a Git o Staging esperando aprobación del líder técnico (Pierre).** | `plane.py update OMNIFY-XXX --state Revisión` |
| **`Pausado`** | **Stopper externo activo** (esperando respuesta de Meta, credenciales, accesos). | `plane.py update OMNIFY-XXX --state Pausado` |
| **`Completado`** | PR mergeado, migración aplicada o entregable validado en producción. | `plane.py update OMNIFY-XXX --state Completado` |
| **`Backlog`** | Idea, deuda técnica descubierta o requerimiento sin fecha inmediata. | `plane.py update OMNIFY-XXX --state Backlog` |
| **`Cancelado`** | Tarea descartada por obsolescencia o cambio de prioridades. | `plane.py update OMNIFY-XXX --state Cancelado` |

---

## 2. Taxonomía de Proyectos, Etiquetas y Prioridades

### A. Proyectos Oficiales:
* **`OMNIFY`:** Código fuente, plataformas web, backend, APIs, integraciones y auditorías de producto.
* **`OPERACIONES` (`OPS`):** Soporte L2/L3 a usuarios, mantenimiento ad-hoc, cuentas Meta, servidores y tickets paraguas semanales.

### B. Etiquetas Humanas (Labels) en Omnify:
* **Componentes / Servicios:** `sms`, `backend`, `frontend`, `bd`, `infra`, `n8n`, `whatsapp`, `acortador`, `tts`, `correo`, `whatsapp-sender`.
* **Naturaleza del Trabajo:** `bug`, `deuda-tecnica`, `seguridad`, `docs`, `question`.

### C. Prioridades Oficiales:
* `urgent` (Caídas de producción, incidentes de facturación, fallos de seguridad).
* `high` (Compromisos del sprint en curso o módulos con bloqueo directo).
* `medium` (Desarrollo estándar o mejoras técnicas programadas).
* `low` / `none` (Deuda técnica menor, optimizaciones cosméticas).

---

## 3. Comandos CLI Disponibles (`plane-tracker` o `scripts/plane.py`)

El script auto-detecta proyectos según el prefijo del ticket (`OMNIFY-162` o `OPS-44`), persiste localmente en SQLite3 (`~/.cache/plane/worklogs.db` con WAL Mode) y carga variables seguras desde `~/.zshrc.local`. Puede invocarse como comando global `plane-tracker` o directamente con Python.

### A. Publicar Bitácora Dual-Layer (Comentario)
```bash
plane-tracker comment OMNIFY-162 -f /tmp/worklog.md
# Con especificación opcional de track y tipo de agente:
plane-tracker comment OMNIFY-162 -f /tmp/worklog.md --track "validaciones" --worker-type "subagent"
```

### B. Crear un Nuevo Ticket / Work Item
```bash
# Crear ticket en Omnify (por defecto) con sugerencia automática de rama Git:
plane-tracker create "[FEAT] Validaciones de esquema en creación de campañas" \
  --priority "high" \
  --labels "backend,performance" \
  -d "Detectada lentitud en la carga de transacciones históricas."

# Crear ticket en otro proyecto corporativo (ej: OPS):
plane-tracker create "[FIX] Mitigar saturación de workers en n8n" \
  -p OPS \
  --state "Pendiente" \
  --priority "urgent"
```

### C. Búsqueda Instantánea en Momento Cero (FTS5 < 2ms)
```bash
# Detectar si ya existe un ticket abierto antes de programar o crear uno nuevo:
plane-tracker search "validaciones formulario"
plane-tracker search "webhook sms" -p OMNIFY
plane-tracker search "soporte ripley" -p OPS

# Salida en JSON para agentes:
plane-tracker search "caddy" --json
```

### D. Generar Reporte de Actividades (Formato Híbrido con Interval Merging)
```bash
# Reporte del día actual (ideal para jefatura a las 6:00 pm):
plane-tracker report --today

# Reporte semanal acumulado (ideal para balance de sprint los viernes):
plane-tracker report --week

# Filtros opcionales por proyecto o formato JSON:
plane-tracker report --today -p OMNIFY
plane-tracker report --today --json
```

### E. Actualizar Estado, Prioridad o Etiquetas
```bash
plane-tracker update OMNIFY-162 \
  --state "Revisión" \
  --priority "high" \
  --labels "sms,backend,bug"
```

### F. Consultar Detalles y Contexto de Relevo (Handoff)
```bash
# Consultar ticket, descripción y comentarios de contexto dejados por Pierre o el equipo:
plane-tracker get OMNIFY-197
plane-tracker get OPS-44
```

### G. Listar Tickets Recientes
```bash
plane-tracker list -p OMNIFY
plane-tracker list -p OPS
```

### H. Listar Proyectos Disponibles (Caché Dinámica en SQLite)
```bash
# Consultar proyectos disponibles en el workspace desde SQLite (< 2ms)
plane-tracker projects

# Forzar refresco desde la API de Plane si se crearon nuevos proyectos
plane-tracker projects --refresh
```

### I. Listar Etiquetas del Proyecto (Caché Dinámica en SQLite)
```bash
# Consultar taxonomía de etiquetas de Omnify (< 2ms)
plane-tracker labels

# Consultar etiquetas de otro proyecto (ej: OPS)
plane-tracker labels -p OPS

# Forzar refresco desde la API de Plane si se agregaron etiquetas nuevas
plane-tracker labels --refresh
```

---

## 4. Estándar de Bitácora Dual-Layer (Humano + Telemetría v2.2)

Todo comentario generado por el asistente al cerrar una sesión debe seguir estrictamente este estándar:

````markdown
### ⏱️ Bitácora de Sesión | [FASE: Auditoría / RFC / PoC / Dev / QA / Soporte / Tooling / Research / Deuda Técnica]

| Parámetro | Detalle |
| :--- | :--- |
| **Fecha & Horario** | YYYY-MM-DD \| HH:MM - HH:MM (Xh Ym) |
| **Frente / Track** | 🎯 `main` / `validaciones` / `datepicker` / `subagent` |
| **Capacidad & Balde** | 🧠 `Deep Work` / 🚀 `Tooling & DX` / 🔬 `Research & I+D` / 🧹 `Tech Debt Paydown` / 🔧 `Toil & Soporte` / 🤝 `Coordinación` |
| **Rol Ejercido** | `Auditor Forense` / `Backend` / `DevOps` / `QA` / `Tooling Architect` / `R&D Researcher` / `Soporte` |
| **Tiempo de Foco** | **Xh Ym netos** (Z min bloqueo / interrupción) |
| **Estado Resultante** | ✅ [Estado actual: Progreso / Pruebas / Revisión / Pausado / Completado] |

#### 🎯 Resumen Ejecutivo de Impacto (Para Gerencia y Jefatura)
- **Diagnóstico / Acción:** Resumen claro y contundente en 2 viñetas comprensibles para líderes.
- **Impacto de Negocio & Retorno:** Riesgo mitigado, créditos salvados, velocidad multiplicada o blindaje de plataforma.
- **Validación / PoC:** Métodos de validación ejecutados (Dry-Run en réplica, tests, simulación o script).

#### 📦 Entregables Verificables
- `ruta/al/archivo_o_script`
- Commit o PR asociado (#XX)

#### ⏭️ Próxima Acción & Dependencias
- Responsable: `Johan Tanta` / `Pierre Vicente` / `Meta`
- Paso siguiente para desbloquear o avanzar.

<!-- PLANE_WORKLOG_METADATA
{
  "schema_version": "2.2",
  "track": "main",
  "worker_type": "human",
  "session_id": "auto-inferido-o-uuid",
  "ticket_id": "OMNIFY-XXX",
  "project": "OMNIFY",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "duration_gross_minutes": 120,
  "duration_net_minutes": 110,
  "focus_time_minutes": 95,
  "interrupted_minutes": 15,
  "bucket": "deep_work",
  "phase": "spike_audit",
  "role": "forensic_auditor",
  "poc_delivered": true,
  "poc_details": {
    "type": "script",
    "path": "ruta/al/script"
  },
  "analysis_paralysis_risk": false,
  "pandora_box_detected": false,
  "pandora_box_details": null,
  "tech_debt_delta": "neutral",
  "tooling_roi": null,
  "research_outcome": null,
  "is_blocked": false,
  "blocked_minutes": 0,
  "blocker_details": null,
  "business_impact": "critical_revenue_risk",
  "deliverables": [
    "ruta/al/archivo"
  ],
  "tests_executed": true,
  "test_run_type": "dry_run_replica",
  "assistant": "antigravity",
  "qualitative_tags": ["forensics", "reconciliacion"]
}
-->
````

---

## 5. Matriz de Inferencia Autógena para Agentes de IA

Para evitar fricción y **nunca** pedirle a Johan que llene formularios manualmente, el asistente deduce los campos a partir de la sesión:

| Huellas en la Sesión (Comandos / Archivos) | Fase Deducida (`phase`) | Balde (`bucket`) | Rol Deducido (`role`) | Impacto (`business_impact`) |
| :--- | :--- | :--- | :--- | :--- |
| Queries SQL forenses, CSVs, dumps, discrepancias | `spike_audit` | `deep_work` | `forensic_auditor` | `critical_revenue_risk` |
| RFCs, diagramas Mermaid, contratos de API | `rfc_design` | `deep_work` | `backend_engineer` | `operational_efficiency` |
| Scripts `.mjs`/`.py` de simulación, PoCs rápidos | `poc_prototype` | `deep_work` | `backend_engineer` | `bug_mitigation` |
| Código frontend/backend, controladores, modelos | `construction_dev` | `deep_work` | `backend / fullstack`| `routine` |
| Dockerfile, compose, Caddy, configs, puertos | `devops_infra` | `deep_work` | `devops_sre` | `operational_efficiency` |
| Vitest, dry-runs SQL con ROLLBACK en réplica | `qa_validation` | `deep_work` | `qa_engineer` | `preventative` |
| Creación de herramientas CLI, Makefile, skills IA | `tooling_dx` | `tooling_dx` | `tooling_architect` | `velocity_multiplier` |
| I+D, estudio de librerías/protocolos de terceros | `research_learning`| `research_rd`| `rd_researcher` | `preventative` |
| Refactorización activa, saneamiento de deuda técnica| `tech_debt_paydown`| `tech_debt_paydown`| `backend_engineer`| `operational_efficiency` |
| Dudas de campañas Ripley, logs de usuarios | `support_l2_l3` | `toil_support` | `support_specialist` | `routine` |

### Señales Estratégicas Clave:
1. **Detección de PoC y Prevención de Parálisis (`poc_delivered`):**
   - Si la sesión ejecutó o creó archivos ejecutables (`.mjs`, `.py`, `.sh`, scripts SQL con resultados) $\rightarrow$ `poc_delivered = true`.
   - Si la sesión duró >120m en diseño conceptual sin código ejecutable $\rightarrow$ `analysis_paralysis_risk = true`.
2. **Detección de "Caja de Pandora" (`pandora_box_detected`):**
   - Se activa si se descubren fallos estructurales imprevistos (ej. *descuadre de 1.6M de filas en SEM-MKT*). El agente extrae el volumen de filas y marca `tech_debt_delta = "discovered"`.
3. **Detección de Bloqueos / Stoppers (`is_blocked`):**
   - Si se concluye en espera de respuesta de Meta, accesos o aprobación de Pierre, marcar `is_blocked: true`, identificar la entidad en `blocker_details`, y sugerir mover a `Pausado`.
4. **Cierre de Sesión:** Presentar la propuesta formateada y pedir confirmación con una sola frase (*"¿Deseas que publique la bitácora dual en Plane con `plane-tracker comment`?"*).

---

## 6. Estándar de Creación de Work Items / Tickets

Cuando un agente o Johan cree un nuevo work item con `plane-tracker create`, debe seguir estrictamente este estándar:

### A. Título
Formato: `[{FASE}] {Acción en infinitivo o resumen conciso en español}`
* Prefijos válidos: `[SPIKE]`, `[RFC]`, `[FEAT]`, `[FIX]`, `[INFRA]`, `[QA]`, `[REFACTOR]`.
* Ejemplos:
  * `[SPIKE] Diagnóstico de concurrencia y rate limit en envíos masivos SMS`
  * `[FEAT] Validaciones de esquema y formulario en creación de campañas`
  * `[FIX] Mitigar error 504 en webhook de recepción de estados de campaña`

### B. Etiquetas (Mínimo 2 etiquetas)
* **Capa Técnica (al menos una):** `backend`, `frontend`, `bd`, `infra`.
* **Naturaleza / Tipo (al menos una):** `bug`, `deuda-tecnica`, `seguridad`, `docs`.
* **Módulo o Canal (si aplica):** `sms`, `whatsapp`, `correo`, `tts`, `acortador`, `n8n`.
* Consulta las etiquetas activas con `plane-tracker labels`.

### C. Plantilla Canónica de la Descripción (Markdown)
```markdown
## Contexto
Breve descripción de la situación actual, componentes o servicios satélite involucrados.

## Problema / Oportunidad
El dolor o la necesidad técnica concreta. ¿Qué falla, qué lentitud existe o qué funcionalidad se requiere?

## Solución Propuesta
Enfoque de solución técnica, diseño de arquitectura, endpoints o lógica de negocio a implementar.

## Requisitos y Restricciones Técnicas
- Compatibilidad con Plane CE v1.2.3, versiones de Node/Python o contenedores Docker.
- Variables de entorno o credenciales requeridas.
- Impacto o dependencias con otros módulos o tablas.

## Criterios de Aceptación (Definition of Done)
- [ ] Pruebas unitarias o de integración pasando.
- [ ] Validación transaccional o verificación end-to-end completada.
- [ ] Rama Git creada bajo el patrón `{tipo}/{TICKET-ID}-{kebab-case}`.
- [ ] Bitácora dual registrada al finalizar con `plane-tracker comment`.
```

### D. Plantilla de Relevo Asíncrono (Handoff Snapshot)
Si dejas una tarea a medias o la devuelves/reasignas a Pierre o al equipo, publica un comentario estructurado de relevo:

```markdown
### 🔄 Relevo de Tarea (Handoff Snapshot)
- **Avance realizado:** Qué se construyó, probó o diagnosticó en esta sesión.
- **Rama Git / Commit:** `feat/OMNIFY-XXX-descripcion` (commit `abcdef1` en remote).
- **Estado actual:** Qué componentes o endpoints están estables y qué se verificó.
- **Stoppers / Próximo paso:** Qué le toca exactamente a quien lo retome para no perder el hilo.
```
