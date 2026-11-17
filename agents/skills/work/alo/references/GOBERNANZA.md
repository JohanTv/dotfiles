# 🏛️ Gobernanza, Living Tickets y Protocolo de Relevo en Plane CE

Directrices complementarias para Allostasis (`alo`). Consultar únicamente bajo los disparadores definidos en `SKILL.md`.

---

## 1. Living Tickets: Estándar Canónico de Pirámide Invertida

Toda descripción de ticket en Plane CE (creada vía `alo ticket create --desc "..."` o interfaz web) DEBE estructurarse bajo la **Pirámide Invertida** (≤ 250 palabras). Queda estrictamente prohibido pegar stack traces completas o volcados JSON extensos en la descripción; esos detalles pertenecen a un comentario vía `alo ticket comment add`.

### Estructura Canónica Obligatoria:

1. **Lead / Resumen (L1):** 1-2 oraciones que resumen el objetivo completo de manera autosuficiente (apto para vistas previas).
2. **Contexto & Causa / Síntoma (L2):** Componentes UI, rutas de archivos, PRs, ramas, endpoints o síntoma observado.
3. **Evidencias & Adjuntos (Multimodal Handoff):** Rutas locales a capturas/grabaciones (`screenshots/...`) o enlaces externos (Figma, Sentry, Swagger).
4. **Solución / Opciones a Evaluar (L3):**
   - Si la solución es conocida (`[FEAT/FIX]`): Enfoque arquitectónico, patrones o librerías.
   - Si está en análisis o incertidumbre (`[SPIKE]`): **Opciones a evaluar** o **hipótesis preliminares** (prohibido inventar soluciones prematuras).
5. **Criterios de Cierre (L4):** Checklists falsables `[ ]` (DoD para construcción; checklist de investigación o veredicto para spikes).

---

## 2. Plantillas Canónicas por Fase

### Fase 1: Incertidumbre / Triage ([SPIKE] o Análisis Pendiente)
```markdown
**Resumen:** [Qué se investiga o analiza y qué se busca resolver].
**Contexto & Síntoma:**
- Módulo / Canal: `omnify-whatsapp` vs `omnify-social-networks`
- Antecedente: [Origen de la necesidad, ej. PR #265 o fallo observado al citar mensajes].
**Evidencias & Adjuntos:**
- Captura UI / Diagrama: `screenshots/2026-11-16_19-41-14.png`
- Trazas / Logs: Ver comentario #1 (evitar saturar la descripción)
**Opciones a Evaluar / Hipótesis:**
- Opción A: [Implementaciones separadas por canal]
- Opción B: [Abstracción común de conversación/mensaje unificado]
- Opción C: [Adapter por canal sobre contrato único]
**Criterio de Salida (Checklist de Investigación):**
- [ ] Matriz de capacidades por canal documentada.
- [ ] Inventario de lo reutilizable en backend/frontend.
- [ ] Recomendación técnica con trade-offs (documento de diseño).
```

### Fase 2: Diseño y Solución ([RFC] o [FEAT/FIX])
```markdown
**Resumen:** [Qué falla y qué se implementará para resolverlo].
**Contexto & Causa Raíz:**
- Componente: `CampaignChipFloatingMenu` (overflow-hidden en acordeón)
- Upstream: PR #265 en origin/dev
**Evidencias & Adjuntos:**
- Captura UI verificada: `screenshots/2026-11-16_19-41-06.png`
- Especificación API: `docs/api_sms_campaign_manual.md`
**Solución Propuesta:**
- Migrar menú a DropdownMenu/Popover con portal al body y colisiones.
- Actualizar selector con line-clamp-2 y botón Eye.
**Criterios de Aceptación (DoD):**
- [ ] Menú flotante no se corta en bordes de acordeón.
- [ ] Selector muestra 2 líneas por ítem y botón Eye.
- [ ] Entorno de trabajo multi-repo configurado vía `alo ws create`.
- [ ] Tests unitarios / npm run check pasando sin errores.
```

---

## 3. Protocolo de Tickets Paraguas Semanales (`OPS`)

* **Propósito:** Absorber interrupciones, ceremonias de equipo y soporte < 15 min sin degradar métricas del sprint en `OMNIFY`.
* **Ubicación:** Proyecto `OPS` exclusivamente. Títulos limpios sin prefijo redundante:
  - `Soporte y Mantenimiento Ad-Hoc - W{XX}` (Capacidad: `toil_support`)
  - `Sincronización de Equipo y Acuerdos - W{XX}` (Capacidad: `coordination`)
* **Cadencia:**
  - **Lunes 09:00 am:** Verificar existencia con `alo ticket search "W{XX}" -p OPS`. Si no existe, crear con `--state Progreso`.
  - **Durante la semana:** Imputar interrupciones con `alo log OPS-XX <MINUTOS> "Detalle" --bucket toil_support`.
  - **Viernes 06:30 pm:** Marcar `Completado` tras balance semanal (`alo load`).

---

## 4. Protocolo de Relevo Asíncrono (Task Handoff)

Al retomar un ticket ajeno o continuado:
1. **Inspección limpia:** Ejecuta `alo ticket get <TICKET-ID> --include comments,history` para extraer intentos previos, estado actual y blockers sin re-investigar lo andado.
2. **Aislamiento de Horas:** Cada registro con `alo log` o `alo ticket comment add` se atribuye a tu usuario activo; no contamina métricas de otros desarrolladores.
3. **Snapshot de Salida:** Si la tarea queda incompleta, publica el comentario estructurado indicado en `SKILL.md` §3 y ejecuta `alo ticket update <ID> --state Pausado`.
