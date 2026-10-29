# 🏷️ Matriz de Taxonomía y Protocolo de Tickets Paraguas
## Catálogo de Etiquetas, Baldes de Capacidad y Gestión de Tareas Sombrilla

**Ámbito:** Gobernanza de TI y Calidad de Datos en Plane CE v1.2.3  
**Proyectos:** `OMNIFY` (ID: `58371da4-cf62-4299-8fd4-99c1052b2eb3`) y `OPS` (ID: `4423b9cd-86dc-4679-853a-90eab846229c`)

---

## 1. Catálogo Vivo de Etiquetas (Labels)

Cada ticket debe poseer **al menos dos etiquetas**: una de capa técnica y una de tipo/módulo.

### 1.1 Proyecto Omnify (`OMNIFY`)

| Etiqueta | Código Hex | Categoría | Uso / Cuándo aplicarla |
| :--- | :---: | :--- | :--- |
| `backend` | `#5E6AD2` | Capa Técnica | Node.js, Express, Nest, controladores, servicios, APIs. |
| `frontend` | `#26B5CE` | Capa Técnica | Vue 3, React, Tailwind, formularios, componentes UI. |
| `bd` | `#F59E0B` | Capa Técnica | PostgreSQL, MySQL, índices, migraciones, queries complejas. |
| `infra` | `#6B7280` | Capa Técnica | Docker, Caddy, Nginx, servidores, variables de entorno. |
| `bug` | `#8ED1FC` | Naturaleza | Errores en producción, excepciones no controladas, fallos 500. |
| `deuda-tecnica`| `#A16207` | Naturaleza | Refactorizaciones, código legado, tipados incompletos. |
| `seguridad` | `#DC2626` | Naturaleza | Autenticación, tokens, endpoints expuestos, sanitización. |
| `docs` | `#46A758` | Naturaleza | Documentación técnica, especificaciones RFC, bitácoras. |
| `question` | `#F78DA7` | Naturaleza | Preguntas de producto, decisiones pendientes con Pierre. |
| `sms` | `#8B5CF6` | Módulo Funcional | Envíos SMS, webhook de estados, proveedores de telefonía. |
| `whatsapp` | `#25D366` | Módulo Funcional | API de Meta, plantillas de WhatsApp, webhooks de mensajes. |
| `whatsapp-sender`| `#128C7E` | Módulo Funcional | Microservicio dedicado a la cola y despacho de WhatsApp. |
| `correo` | `#0EA5E9` | Módulo Funcional | Envío de correos transaccionales, SMTP, plantillas HTML. |
| `tts` | `#F97316` | Módulo Funcional | Text-to-Speech, llamadas automatizadas de voz. |
| `acortador` | `#14B8A6` | Módulo Funcional | Redirección de URLs cortas, métricas de clics. |
| `n8n` | `#EA4B71` | Módulo Funcional | Workflows automatizados en n8n, triggers y webhooks. |

---

### 1.2 Proyecto Operaciones (`OPS`)

| Etiqueta | Código Hex | Categoría | Uso / Cuándo aplicarla |
| :--- | :---: | :--- | :--- |
| `externo` | `#7BDCB5` | Clasificación | Solicitudes originadas por clientes (ej. Ripley, Falabella). |
| `meta` | `#0866FF` | Clasificación | Cuentas comerciales de Meta, WABA, líneas bloqueadas. |
| `backend` | `#5E6AD2` | Capa Técnica | Revisión de scripts, fixes operativos en APIs. |
| `bd` | `#F59E0B` | Capa Técnica | Consultas manuales de saldos, dumps, reconciliación. |
| `infra` | `#6B7280` | Capa Técnica | Mantenimiento de servidores, certificados SSL, Caddy. |
| `bug` | `#8ED1FC` | Naturaleza | Incidencias operativas no programadas. |
| `deuda-tecnica`| `#A16207` | Naturaleza | Toil recurrente candidato a automatización. |
| `seguridad` | `#DC2626` | Naturaleza | Permisos, accesos a base de datos, credenciales. |
| `docs` | `#46A758` | Naturaleza | Manuales operativos, minutas de reuniones. |

---

## 2. Baldes de Capacidad (`capacity_bucket`)

Para el reporte dual-layer y el análisis de distribución de tiempo del desarrollador:

| Balde | Nombre Visible | Definición | Objetivo Saludable |
| :--- | :--- | :--- | :---: |
| `deep_work` | 🧠 Deep Work | Programación dura, arquitectura, resolución de bugs complejos. | **50% - 60%** |
| `toil_support` | 🔧 Toil & Soporte | Atención ad-hoc a usuarios, consultas manuales, tareas repetitivas. | **15% - 20%** |
| `coordination` | 🤝 Coordinación | Dailies, 1:1s con Pierre, syncs de equipo, demos. | **10% - 15%** |
| `tooling_dx` | 🚀 Tooling & DX | Creación de scripts CLI, mejoras de dotfiles, optimización de agentes. | **5% - 10%** |
| `research_rd` | 🔬 Research & I+D| Investigación de librerías, evaluación de protocolos, benchmarks. | **5% - 10%** |
| `tech_debt_paydown`| 🧹 Tech Debt | Refactorización activa y saneamiento de código obsoleto. | **5% - 10%** |

---

## 3. Protocolo de Tickets Paraguas Semanales

### 3.1 Justificación
Evitar la dispersión de tiempo en el reporte diario para el jefe sin ensuciar el backlog del sprint con decenas de micro-tickets menores a 15 minutos.

### 3.2 Los Dos Tickets Semanales

```
┌────────────────────────────────────────────────────────┐
│            TICKETS PARAGUAS DE LA SEMANA W{XX}         │
├────────────────────────────┬───────────────────────────┤
│ En Proyecto: OPS           │ En Proyecto: OMNIFY       │
│ [OPS] Soporte L2/L3 y Man- │ [SYNC] Ceremonias de      │
│ tenimiento Ad-Hoc - W{XX}  │ Equipo y Dailies - W{XX}  │
│ Capacidad: toil_support    │ Capacidad: coordination   │
└────────────────────────────┴───────────────────────────┘
```

### 3.3 Cadencia de Operación
1. **Lunes 09:00 am (Apertura):**
   - El desarrollador o el asistente verifica si existe el ticket de la semana (`W{ISO_WEEK}`).
   - Si no existe, se crea con estado `Progreso`.
2. **Durante la semana (Append-Only):**
   - Cada interrupción o reunión se comenta usando flags de track:
     ```bash
     plane-tracker comment OPS-44 --track "soporte-ripley" --capacity "toil_support" -m "..."
     plane-tracker comment OMNIFY-185 --track "daily-pierre" --capacity "coordination" -m "..."
     ```
3. **Viernes 06:30 pm (Cierre):**
   - Se ejecuta el balance con `plane-tracker report --week`.
   - El ticket paraguas se transiciona a `Completado`:
     ```bash
     plane-tracker update OPS-44 --state "Completado"
     plane-tracker update OMNIFY-185 --state "Completado"
     ```
