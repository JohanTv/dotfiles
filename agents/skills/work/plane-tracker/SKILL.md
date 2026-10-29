---
name: plane-tracker
description: Registra bitácoras de sesión, tiempos y entregables en Plane (Omnify/Operaciones) bajo el patrón dual-layer (humano + metadata oculta). Úsalo al cerrar sesiones o al finalizar hitos de auditoría o desarrollo.
---

# Plane Session Tracker & Worklog Operator

Procedimiento operativo para registrar sesiones de trabajo, diagnósticos y avances de desarrollo en la plataforma Plane auto-hospedada de la empresa.

---

## 1. Verificación de Variables de Entorno

Antes de invocar operaciones de Plane, el entorno debe tener configuradas las siguientes variables (definidas en `~/.zshrc.local`):

* `PLANE_BASE_URL`: URL base de la instancia interna (ej. `http://plane.example.com`).
* `PLANE_API_KEY`: API token de cuenta de usuario.
* `PLANE_WORKSPACE_SLUG`: Slug del espacio de trabajo (por defecto: `mi-workspace`).
* `PLANE_PROJECT_ID`: ID del proyecto (por defecto para Omnify: `<uuid-proyecto>`).

Si alguna variable falta, solicita amablemente al usuario configurarla en `~/.zshrc.local` o emite el texto formateado en el chat para que el usuario pueda copiarlo y pegarlo manualmente.

---

## 2. El Formato Dual-Layer (Capa Humana + Capa Máquina)

Todo comentario de sesión debe cumplir con el siguiente estándar:

```markdown
### ⏱️ Registro de Sesión | [FASE: Auditoría / Análisis / Dev / QA / Soporte]

| Métrica | Detalle |
| :--- | :--- |
| **Fecha** | YYYY-MM-DD |
| **Horario** | HH:MM - HH:MM (Xh Ym) |
| **Tipo de Trabajo** | `Auditoría` / `Análisis` / `Construcción` / `QA` / `Soporte` |
| **Responsable** | [mantenedor] |
| **Estado Resultante** | ✅ Hito Concluido / En Progreso |

#### 🎯 Resumen Ejecutivo
- Resumen conciso de 2-3 puntos clave entendibles por jefatura y gerencia.
- Causa raíz identificada o problema de negocio resuelto.

#### 📦 Entregables Verificables
- Archivos creados, scripts SQL, ramas o PRs generados en la sesión.

#### ⏭️ Próxima Acción
- Siguiente paso técnico inmediato o requerimiento pendiente.

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
    "ruta/al/archivo1",
    "ruta/al/archivo2"
  ]
}
-->
```

---

## 3. Publicación Automatizada del Comentario

Para publicar el comentario en el ticket objetivo (`OMNIFY-XXX` o número de secuencia):

```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane_post.py OMNIFY-XXX -m "CONTENIDO_DEL_COMENTARIO"
```

O guardando el comentario en un archivo temporal:
```bash
python3 ~/.agents/skills/plane-tracker/scripts/plane_post.py OMNIFY-XXX -f /tmp/comentario.md
```
