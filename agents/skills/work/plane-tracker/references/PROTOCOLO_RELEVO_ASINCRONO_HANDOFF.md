# 🤝 Protocolo de Relevo Asíncrono de Tareas (Task Handoff)
## Continuidad Operativa, Ingestión de Contexto y Aislamiento de Telemetría

**Ámbito:** Trabajo colaborativo entre miembros del equipo (`Pierre Vicente`, `Johan Tanta`, etc.) y agentes de IA.  
**Propósito:** Retomar tareas iniciadas por otros desarrolladores sin perder contexto, destilando notas de handoff y manteniendo aislada la autoría de las horas en Plane CE v1.2.3.

---

## 1. El Problema Operativo del Relevo
En un equipo ágil de ingeniería:
1. Pierre crea un ticket, realiza pruebas preliminares, encuentra dificultades o blockers, deja comentarios y asigna el ticket a Johan.
2. Si Johan abre una sesión y el agente no sabe leer los comentarios previos, Johan gasta 30 minutos re-investigando lo que Pierre ya descubrió.
3. Si el agente computa horas sobre el ticket, arriesga mezclar las horas de Pierre con las de Johan, distorsionando el reporte de las 6:00 pm para la jefatura.

---

## 2. El Ciclo de 4 Etapas del Relevo

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Localización del Ticket (Momento Cero):                             │
│    plane-tracker search "<tema>" ➔ Detecta OMNIFY-XXX (< 80ms)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. Ingesta y Destilación de Contexto:                                  │
│    plane-tracker get <TICKET> ➔ Descarga descripción + comentarios     │
│    El agente aísla: Intentos previos, estado actual y próximo paso     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. Ejecución & Telemetría Aislada:                                     │
│    git checkout -b {tipo}/{TICKET-ID}-{kebab}                          │
│    Johan trabaja y registra sus horas con plane-tracker comment        │
│    (Las horas se imputan a Johan; el historial de Pierre no se toca)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                  ¿Se termina o se vuelve a dejar a medias?
                                    │
                 ┌──────────────────┴──────────────────┐
                 │ TERMINADO                           │ A MEDIAS
                 ▼                                     ▼
   ┌───────────────────────────┐         ┌───────────────────────────┐
   │ Marcar DoD [x]            │         │ Publicar Handoff Snapshot │
   │ Bitácora dual de cierre   │         │ Pierre retoma en 5 seg    │
   └───────────────────────────┘         └───────────────────────────┘
```

---

## 3. Ingesta Inteligente de Contexto (`plane-tracker get`)

Al ejecutar:
```bash
plane-tracker get OMNIFY-197
```

El CLI devuelve en la terminal la descripción y los comentarios cronológicos limpios:
```text
📌 OMNIFY-197: Conector de Plane para claude.ai (MCP remoto)
   • Prioridad : NONE | Creado el : 2026-10-29
   • UUID      : 82a30db4-00ec-4b70-be2d-1cf55af59ba2

📄 Descripción:
   El equipo gestiona el proyecto Omnify en un Plane autoalojado...

💬 Contexto de Relevo / Comentarios (2):
   [1] (2026-10-29 16:35): Requisitos previos: OMNIFY-198 (actualizar Plane de v1.2.3 a v1.4.3), OMNIFY-199 (DNS y HTTPS).
   [2] (2026-10-29 16:31): Análisis de factibilidad: Veredicto: factible sin cambiar de versión. La 0.2.9 ya trae modo HTTP...
```

### Reglas de Extracción para Asistentes de IA:
El asistente debe destilar la información ignorando logs crudos extensos y respondiendo con 4 puntos:
1. **Qué intentó el colega anterior:** (ej. *"Pierre probó el modo HTTP en puerto 8211"*).
2. **Qué funcionó:** (ej. *"El arranque y rechazo funcionaron en local"*).
3. **Stoppers / Prerrequisitos identificados:** (ej. *"Falta token de bot y HTTPS"*).
4. **Próximo paso de ingeniería:** (ej. *"Probar autenticación del bot token y armar Dockerfile"*).

---

## 4. Aislamiento de Horas y Telemetría

* **No se mezclan horas:**  
  En Plane CE, cada comentario almacena el autor que lo publicó (`created_by`).
* **Cálculo en SQLite:**  
  La base de datos local `worklogs.db` asocia cada bloque de trabajo a la sesión activa.
* **Reporte a Jefatura (`plane-tracker report --today`):**  
  A las 6:00 pm, Johan solo le reporta a Pierre el tiempo que **Johan** efectivamente dedicó durante ese día a ese ticket, garantizando transparencia absoluta.

---

## 5. El Relevo Inverso: Plantilla de Handoff Snapshot

Si Johan no concluye la tarea durante su turno y debe suspenderla o devolvérsela a Pierre, debe publicar obligatoriamente un **Handoff Snapshot** antes de cerrar la sesión:

```bash
plane-tracker comment OMNIFY-197 --duration 10 -m "### 🔄 Relevo de Tarea (Handoff Snapshot)
- **Avance realizado:** Se configuró el usuario bot en Plane y se validó la petición HTTP con curl.
- **Rama Git / Commit:** infra/OMNIFY-197-claude-mcp-connector (commit a81f3e en origin).
- **Estado actual:** El servidor responde 200 OK localmente con el bot token.
- **Stoppers / Próximo paso:** Falta empaquetar en contenedor Docker y levantar túnel Cloudflare."
```

### Estructura Canónica:
```markdown
### 🔄 Relevo de Tarea (Handoff Snapshot)
- **Avance realizado:** Qué se construyó, probó o diagnosticó en esta sesión.
- **Rama Git / Commit:** `{tipo}/{TICKET-ID}-{kebab}` (commit `{hash}` en remote).
- **Estado actual:** Qué componentes o endpoints están estables y qué se verificó.
- **Stoppers / Próximo paso:** Qué le toca exactamente a quien lo retome para no perder el hilo.
```
