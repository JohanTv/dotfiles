# 📚 Suite de Referencias: Gobernanza, SDLC y Protocolos de Operación

Esta carpeta agrupa los protocolos operativos, taxonomías y directrices de gobernanza de software que utiliza el equipo y los asistentes de IA (**Antigravity CLI / agy**, **Claude Code**, **OpenCode**) operando a través de **Allostasis (`alo`)** y **Plane CE v1.2.3**.

---

## 🗺️ Mapa de Protocolos y Guías

1. [🔄 **Protocolo de Living Tickets y Fases del SDLC**](./PROTOCOLO_LIVING_TICKETS_Y_SDLC.md)
   * El ciclo de 4 fases (`[SPIKE]`, `[RFC]`, `[FEAT/FIX]`, `[QA]`), la regla de los 15 minutos y las 3 plantillas evolutivas para gestionar la incertidumbre sin micro-tickets basura.
2. [🤝 **Protocolo de Relevo Asíncrono de Tareas (Task Handoff)**](./PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md)
   * Cómo tomar tickets iniciados por otra persona del equipo, destilar el contexto de comentarios previos, aislar telemetría y publicar Handoff Snapshots si se deja a medias.
3. [🏷️ **Matriz de Taxonomía y Protocolo de Tickets Paraguas**](./MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md)
   * Catálogo de etiquetas en Omnify y OPS, baldes de capacidad y ciclo de vida de tickets semanales para reuniones y toil.
4. [📋 **Estrategia Integral de Gestión TI y Work Items**](./ESTRATEGIA_GESTION_TI_Y_WORKITEMS.md)
   * Visión de alto rendimiento, arquetipos de ingeniería y diseño del dashboard personal.
5. [🛡️ **Gobernanza y Principios de Diseño del CLI**](./CLI_DESIGN_GUARD.md)
   * Los 6 invariantes arquitecturales (CQS, ortogonalidad, jerarquía sustantivo+verbo), protocolo de 5 filtros ("Antes de agregar un flag") y límites ratchet.

---

## ⚡ Comandos Canónicos de Referencia en Allostasis (`alo`)

```bash
# Momento Cero: búsqueda en la caché local (título y etiquetas)
alo ticket search "validaciones formulario" --limit 5 --json

# Crear ticket con sugerencia de rama según fase
alo ticket create "[FEAT] Validaciones de esquema SMS" -p OMNIFY --priority high --labels "backend,sms"

# Inspeccionar ticket con comentarios y contexto del equipo
alo ticket get OMNIFY-197

# Registrar sesión de trabajo rápido o soporte en un solo paso
alo log OPS-44 15

# Revisar carga cognitiva y tiempo neto libre de solapamientos (Klee)
alo load
```
