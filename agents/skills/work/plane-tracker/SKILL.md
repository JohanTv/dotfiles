---
name: plane-tracker
description: Orquestador y registrador de tareas, estados, prioridades, etiquetas y bitácoras en Plane (Omnify/Operaciones) bajo el patrón dual-layer. Úsalo al iniciar tareas, al pasar a Pruebas/Revisión de PR, al cerrar sesiones o al finalizar hitos.
---

# Plane Session Tracker & Worklog Operator

Procedimiento operativo integral para interactuar con la plataforma Plane CE v1.2.3 auto-hospedada de la empresa (Omnify / Operaciones).

---

## 1. Mapeo de Estados y Ciclo de Vida del Ticket

El proyecto **Omnify** cuenta con 8 estados oficiales. Los asistentes deben realizar transiciones deterministas según el hito del desarrollador:

| Estado en Plane | ¿Cuándo se activa? (Triggers del Asistente) | Comando CLI |
| :--- | :--- | :--- |
| **`Pendiente`** | Tarea asignada o planificada pero aún no iniciada. | `plane.py update OMNIFY-XXX --state Pendiente` |
| **`Progreso`** | Johan arranca a investigar, auditar o programar la tarea. | `plane.py update OMNIFY-XXX --state Progreso` |
| **`Pruebas`** | Código/script listo; ejecutando dry-run transaccional, tests unitarios o validación con réplica. | `plane.py update OMNIFY-XXX --state Pruebas` |
| **`Revisión`** | **PR subido a Git / Staging en espera de aprobación del líder técnico (Pierre).** | `plane.py update OMNIFY-XXX --state Revisión` |
| **`Pausado`** | Bloqueo externo (esperando respuesta de Meta, credenciales, acceso a servidor). | `plane.py update OMNIFY-XXX --state Pausado` |
| **`Completado`** | PR mergeado, migración ejecutada o entregable verificado en producción. | `plane.py update OMNIFY-XXX --state Completado` |
| **`Backlog`** | Idea o deuda técnica sin fecha de ejecución inmediata. | `plane.py update OMNIFY-XXX --state Backlog` |

---

## 2. Taxonomía de Etiquetas (Labels) y Prioridades en Omnify

### Etiquetas Disponibles:
* **Componentes / Servicios:** `sms`, `backend`, `frontend`, `bd`, `infra`, `n8n`, `whatsapp`, `acortador`, `tts`, `correo`, `whatsapp-sender`.
* **Área / Tipo de Esfuerzo:** `bug`, `deuda-tecnica`, `seguridad`, `docs`, `question`.

### Prioridades Disponibles:
* `urgent` (Caídas de producción, incidentes críticos, subfacturación activa).
* `high` (Tareas del sprint o módulo actual comprometidas para entrega).
* `medium` (Desarrollo estándar o mejoras planificadas).
* `low` / `none` (Deuda técnica menor, cosméticos).

---

## 3. Comandos CLI Disponibles (`scripts/plane.py`)

El script auto-carga variables desde `~/.zshrc.local` si no están en el entorno.

### A. Actualizar Estado, Prioridad o Etiquetas
```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane.py update OMNIFY-162 \
  --state "Revisión" \
  --priority "high" \
  --labels "sms,backend,bug"
```

### B. Publicar Bitácora Dual-Layer (Comentario)
```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane.py comment OMNIFY-162 -f /tmp/worklog.md
```

### C. Consultar Detalles de un Ticket
```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane.py get OMNIFY-162
```

### D. Listar Tickets Recientes del Proyecto
```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane.py list
```

---

## 4. Estándar de la Bitácora Dual-Layer (Comentario)

Todo comentario generado por el asistente debe seguir este formato exacto:

```markdown
### ⏱️ Registro de Sesión | [FASE: Auditoría / Análisis / Dev / QA / Soporte]

| Métrica | Detalle |
| :--- | :--- |
| **Fecha** | YYYY-MM-DD |
| **Horario** | HH:MM - HH:MM (Xh Ym) |
| **Tipo de Trabajo** | `Auditoría` / `Análisis` / `Construcción` / `QA` / `Soporte` |
| **Responsable** | Johan Tanta |
| **Estado Resultante** | ✅ [Estado actual: Progreso / Pruebas / Revisión / Completado] |

#### 🎯 Resumen Ejecutivo para Gerencia
- Resumen conciso de 2-3 puntos clave con impacto de negocio.

#### 📦 Entregables Verificables
- Archivos generados, scripts SQL, commits o PR (#XX).

#### ⏭️ Próxima Acción
- Siguiente paso (ej. *"Esperando aprobación de PR por Pierre Vicente"*).

<!-- PLANE_WORKLOG_METADATA
{
  "version": "1.0",
  "ticket": "OMNIFY-XXX",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "duration_minutes": 0,
  "phase": "auditoria|analisis|construccion|qa|soporte",
  "developer": "johantv",
  "deliverables": [
    "ruta/al/archivo"
  ]
}
-->
```
