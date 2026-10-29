# Protocolo de Trabajo y Tracking TI (Work Context)

### Ámbito y Gobernanza:
- **Entorno:** Aplica en repositorios de trabajo (`Omnify`, `Operaciones`, servicios satélite en `Code/`).
- **Ciclo de 4 Fases (SDLC):** Todo requerimiento técnico se clasifica en:
  1. `[SPIKE]` **Auditoría / Diagnóstico:** Forense de datos, análisis de causa raíz e informes técnicos.
  2. `[RFC]` **Análisis de Implementación:** Modelado de schema, contratos de API y diseño previo.
  3. `[FEAT/FIX/INFRA]` **Construcción & DevOps:** Desarrollo de código, Docker, compose y variables.
  4. `[QA]` **Testing & Validación:** Pruebas transaccionales, recálculo, dry-run con réplicas.

### Registro de Tiempos y Telemetría en Plane:
- **Skill Obligatoria:** Utiliza la skill `plane-tracker` para interactuar con la API de Plane (definida en `$PLANE_BASE_URL`).
- **Hitos de Activación:** Al concluir un artefacto diagnóstico (informe/scripts) o al finalizar una sesión de trabajo, redacta la bitácora dual (tabla ejecutiva + metadata oculta `PLANE_WORKLOG_METADATA`) y sugiere registrarla en el ticket respectivo.
- **Toil y Reuniones (Tickets Paraguas):** Soporte ad-hoc a usuarios y reuniones se registran en tickets semanales consolidados en `OPS`; nunca crees micro-tickets para tareas de menos de 15 minutos.

### Convención de Ramas Git (Work Context vs Personal):
- **Ámbito Corporativo / Work (Plane):** Cuando se trabaje en repositorios corporativos de trabajo, toda rama debe seguir estrictamente el patrón:
  `{tipo}/{TICKET-ID}-{kebab-case-descripcion}`
  - Tipos válidos: `spike`, `feat`, `fix`, `refactor`, `test`, `infra` (alineados a las 4 fases).
  - **Proyecto por defecto:** Actualmente se considera principalmente **Omnify** (`OMNIFY-`).
  - **Proyectos dinámicos:** La organización cuenta con proyectos dinámicos (`OMNIFY`, `OPS`, `OMNICANAL`, etc.) cacheados en SQLite. Usa `plane-tracker projects` para inspeccionarlos.
  - Ejemplos:
    - `feat/OMNIFY-175-campaign-form-validations`
    - `fix/OMNIFY-180-fix-date-picker`
    - `spike/OMNIFY-162-sms-concurrency-audit`
    - `fix/OPS-44-mitigate-n8n-stoppers`
- **Manejo de Ambigüedad:** Si el usuario solicita crear una rama o iniciar una tarea sin mencionar el ticket de Plane, el agente debe preguntar brevemente (ej. *"¿A qué ticket de Omnify asociamos esta rama?"*) antes de crearla.
- **Proyectos Personales / Sin Plane:** Si el contexto es un proyecto personal, de código abierto o no vinculado a Plane, no forzar ticket ID; usar el formato convencional estándar: `{tipo}/{kebab-case-descripcion}`.

### Detección y Momento Cero (Zero-Moment Discovery):
- **Búsqueda Instantánea:** Al iniciar una sesión o recibir una intención de trabajo (ej. *"arreglemos las validaciones del formulario"*), el agente debe ejecutar `plane-tracker search "<intención>"` para comprobar en < 2ms si ya existe un ticket abierto en Plane o si se debe proponer uno nuevo.
- **Acción Rápida:** Si hay un ticket coincidente, preguntar brevemente para confirmar y cambiar a la rama respectiva (`git checkout -b feat/OMNIFY-XXX-...`). Si no existe, proponer el work item con título, prioridad y etiquetas.

### Estándar de Creación y Ciclo de Vida de Work Items:
- **Título:** Estructurado como `[{FASE}] {Acción o resumen conciso en español}`
  - Fases válidas: `[SPIKE]`, `[RFC]`, `[FEAT]`, `[FIX]`, `[INFRA]`, `[QA]`, `[REFACTOR]`.
  - El módulo se menciona naturalmente en el texto (ej. `[FEAT] Validaciones de formulario en campañas SMS`). No usar corchetes dobles para evitar truncamiento en tarjetas Kanban.
- **Taxonomía de Etiquetas (Mínimo 2 etiquetas):**
  - Capa técnica: `backend`, `frontend`, `bd`, `infra`.
  - Tipo o naturaleza: `bug`, `deuda-tecnica`, `seguridad`, `docs`.
  - Módulo específico (si aplica): `sms`, `whatsapp`, `correo`, `tts`, `acortador`, `n8n`.
  - Consulta etiquetas vivas en SQLite con `plane-tracker labels`.
- **Living Ticket Pattern (Regla de los 15 Minutos):**
  - **Tareas < 15 min (Toil/Soporte):** No crear ticket formal en el proyecto activo; absorber en el ticket paraguas semanal de `OPS`.
  - **Tareas > 15 min:** Crear ticket formal en Plane. Si se inicia en incertidumbre (`[SPIKE]` o `[FIX]`), la descripción inicial documenta *Contexto*, *Síntoma observado*, *Comportamiento esperado* e *Hipótesis*. Al aislar la causa raíz, se actualiza con la *Solución Propuesta* y *Criterios de Aceptación (DoD)*.
- **Tickets Paraguas Semanales (Cadencia W{ISO_WEEK}, ambos viven en `OPS`):** El identifier del proyecto ya aporta el contexto, por eso el título no repite `[OPS]` ni usa jerga de gestión (evitar `L2/L3`, `SYNC`, `Ceremonias`).
  - Soporte / toil: `Tareas Rápidas y Soporte - W{XX}` (capacidad: `toil_support`).
  - Coordinación de equipo: `Reuniones de Equipo y Acuerdos - W{XX}` (capacidad: `coordination`).
  - Cada intervención se registra con `plane-tracker comment <TICKET> --track "<tema>" --capacity "<balde>" --duration <minutos>`.
  - **La duración nunca se estima:** si el trabajo se hizo fuera de la conversación (ej. configurar una firma en el cliente de correo) y el agente no lo observó, **pregunta primero** cuánto demoró; si el usuario no lo sabe, no se registra el tiempo todavía.
- **Protocolo de Relevo Asíncrono (Task Handoff):**
  - **Al tomar un ticket ajeno (ej. de Pierre):** El agente ejecuta `plane-tracker get <TICKET>` para destilar automáticamente el contexto útil de los comentarios previos (qué se probó, qué funcionó, stoppers y próximo paso inmediato). Las horas efectivas se imputan a nombre propio con `plane-tracker comment` sin alterar el cómputo del autor anterior.
  - **Al dejar una tarea a medias:** Publicar un comentario estructurado de relevo (*Handoff Snapshot*) con: avance realizado, rama/commit actual, estado del arte y pendientes inmediatos para quien lo retome.
