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
- **Toil y Reuniones (Tickets Paraguas):** Soporte ad-hoc a usuarios y reuniones se registran en tickets semanales consolidados en `Operaciones` u `Omnify`; nunca crees micro-tickets para tareas de menos de 15 minutos.

### Convención de Ramas Git (Work Context vs Personal):
- **Ámbito Corporativo / Work (Plane):** Cuando se trabaje en repositorios corporativos de trabajo, toda rama debe seguir estrictamente el patrón:
  `{tipo}/{TICKET-ID}-{kebab-case-descripcion}`
  - Tipos válidos: `spike`, `feat`, `fix`, `refactor`, `test`, `infra` (alineados a las 4 fases).
  - **Proyecto por defecto:** Actualmente se considera principalmente **Omnify** (`OMNIFY-`).
  - **Proyectos dinámicos:** La organización cuenta con proyectos dinámicos (`OMNIFY`, `OPS`, `OMNICANAL`, etc.) cacheados en SQLite. Usa `plane projects` para inspeccionarlos.
  - Ejemplos:
    - `feat/OMNIFY-175-campaign-form-validations`
    - `fix/OMNIFY-180-fix-date-picker`
    - `spike/OMNIFY-162-sms-concurrency-audit`
    - `fix/OPS-44-mitigate-n8n-stoppers`
- **Manejo de Ambigüedad:** Si el usuario solicita crear una rama o iniciar una tarea sin mencionar el ticket de Plane, el agente debe preguntar brevemente (ej. *"¿A qué ticket de Omnify asociamos esta rama?"*) antes de crearla.
- **Proyectos Personales / Sin Plane:** Si el contexto es un proyecto personal, de código abierto o no vinculado a Plane, no forzar ticket ID; usar el formato convencional estándar: `{tipo}/{kebab-case-descripcion}`.
