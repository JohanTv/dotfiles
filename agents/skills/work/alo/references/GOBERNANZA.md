# 🏛️ Gobernanza, Living Tickets y Protocolo de Relevo en Plane CE

Directrices complementarias para Allostasis (`alo`). Consultar únicamente bajo los disparadores definidos en `SKILL.md`.

---

## 1. Living Tickets: Plantillas por Fase

### Fase 1: Incertidumbre / Triage ([SPIKE] / Bug no aislado)
Aplica principio de pirámide invertida (≤ 200 palabras). Las trazas o logs extensos se publican como comentario vía `alo ticket comment add`, nunca en la descripción.

```markdown
**Resumen:** [Qué falla exactamente y qué anomalía se investiga].
**Contexto & Síntoma:**
- Módulo: `nombre_modulo`
- Anomalía: [1 párrafo conciso con códigos o discrepancias clave].
**Hipótesis Preliminares:**
- [ ] Hipótesis A: [Posible causa]
- [ ] Hipótesis B: [Posible causa]
**Plan de Investigación (Checklist):**
- [ ] Reproducir con payload en réplica local o tests.
- [ ] Aislar línea o condición de carrera.
```

### Fase 2: Diseño y Solución ([RFC] / Causa Aislada)
```markdown
**Resumen:** [Qué se implementará para resolver el problema].
**Causa Raíz:** [Explicación técnica concisa].
**Solución Propuesta:** 1. [Enfoque técnico] 2. [Patrón / Migración].
**Criterios de Aceptación (DoD):**
- [ ] Parche defensivo implementado.
- [ ] Migración con rollback seguro (si aplica).
- [ ] Rama Git `{tipo}/{TICKET-ID}-{kebab}`.
- [ ] Tests unitarios/integración pasando.
```

---

## 2. Protocolo de Tickets Paraguas Semanales (`OPS`)

* **Propósito:** Absorber interrupciones, ceremonias de equipo y soporte < 15 min sin degradar métricas del sprint en `OMNIFY`.
* **Ubicación:** Proyecto `OPS` exclusivamente. Títulos limpios sin prefijo redundante:
  - `Soporte y Mantenimiento Ad-Hoc - W{XX}` (Capacidad: `toil_support`)
  - `Sincronización de Equipo y Acuerdos - W{XX}` (Capacidad: `coordination`)
* **Cadencia:**
  - **Lunes 09:00 am:** Verificar existencia con `alo ticket search "W{XX}" -p OPS`. Si no existe, crear con `--state Progreso`.
  - **Durante la semana:** Imputar interrupciones con `alo log OPS-XX <MINUTOS> "Detalle" --bucket toil_support`.
  - **Viernes 06:30 pm:** Marcar `Completado` tras balance semanal (`alo load`).

---

## 3. Protocolo de Relevo Asíncrono (Task Handoff)

Al retomar un ticket ajeno o continuado:
1. **Inspección limpia:** Ejecuta `alo ticket get <TICKET-ID> --json` para extraer intentos previos, estado actual y blockers sin re-investigar lo andado.
2. **Aislamiento de Horas:** Cada registro con `alo log` o `alo ticket comment add` se atribuye a tu usuario activo; no contamina métricas de otros desarrolladores.
3. **Snapshot de Salida:** Si la tarea queda incompleta, publica el comentario estructurado indicado en `SKILL.md` §3 y ejecuta `alo ticket update <ID> --state Pausado`.
