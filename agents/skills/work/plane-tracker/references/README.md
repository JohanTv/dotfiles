# 📚 Suite de Documentación: Tracking, Telemetría y Plane CE v1.2.3

Bienvenido a la especificación técnica y operativa del ecosistema de tracking y telemetría de ingeniería de Johan Tanta, diseñado para operar de forma transparente con **Plane CE v1.2.3** y asistentes de IA (**Antigravity CLI / agy**, **Claude Code**, **OpenCode**).

---

## 🗺️ Mapa de Documentos

1. [🏛️ **Arquitectura del Sistema de Tracking y Telemetría**](./ARQUITECTURA_SISTEMA_TRACKING_Y_TELEMETRIA.md)
   * Visión general, dual-layer pattern, SQLite3 WAL mode, Klee's Interval Merging y optimización de tokens.
2. [🔄 **Protocolo de Living Tickets y Fases del SDLC**](./PROTOCOLO_LIVING_TICKETS_Y_SDLC.md)
   * El ciclo de 4 fases (`[SPIKE]`, `[RFC]`, `[FEAT/FIX]`, `[QA]`), la regla de los 15 minutos y las 3 plantillas evolutivas para gestionar la incertidumbre.
3. [🤝 **Protocolo de Relevo Asíncrono de Tareas (Task Handoff)**](./PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md)
   * Cómo tomar tickets iniciados por Pierre o el equipo, destilar el contexto de comentarios previos, aislar telemetría y publicar Handoff Snapshots si se deja a medias.
4. [🛠️ **Guía Operativa del CLI `plane-tracker`**](./GUIA_OPERATIVA_CLI_PLANE_TRACKER.md)
   * Manual exhaustivo de comandos (`search`, `create`, `get`, `update`, `comment`, `labels`, `projects`, `report`) con flags, ejemplos y salidas JSON.
5. [🏷️ **Matriz de Taxonomía y Protocolo de Tickets Paraguas**](./MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md)
   * Catálogo de 16 etiquetas en Omnify, 11 en OPS, baldes de capacidad y ciclo de vida de tickets semanales para reuniones y toil.
6. [📋 **Estrategia Integral de Gestión TI y Work Items**](./ESTRATEGIA_GESTION_TI_Y_WORKITEMS.md)
   * Visión de alto rendimiento, arquetipos de ingeniería y diseño del dashboard personal.

---

## ⚡ Comandos Rápidos de Referencia

```bash
# Momento Cero: Búsqueda instantánea FTS5 (< 2ms)
plane-tracker search "validaciones formulario"

# Crear ticket con sugerencia de rama según fase
plane-tracker create "[FEAT] Validaciones de esquema SMS" -p OMNIFY --priority high --labels "backend,sms"

# Inspeccionar ticket con comentarios y contexto de Pierre
plane-tracker get OMNIFY-197

# Reporte para Pierre a las 6:00 pm (Interval Merging de Klee)
plane-tracker report --today
```
