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
- **Ámbito Omnify / Operaciones (Work):** Cuando se trabaje en repositorios corporativos vinculados a Plane, toda rama debe seguir estrictamente el patrón:
  `{tipo}/{TICKET-ID}-{kebab-case-descripcion}`
  - Tipos válidos: `spike`, `feat`, `fix`, `refactor`, `test`, `infra` (alineados a las 4 fases).
  - Ejemplos:
    - `feat/OMNIFY-175-campaign-form-validations`
    - `fix/OPS-44-mitigate-n8n-stoppers`
    - `spike/OMNIFY-162-sms-concurrency-audit`
    - `refactor/OMNIFY-171-docker-node24`
- **Manejo de Ambigüedad:** Si el usuario solicita crear una rama o iniciar una tarea sin mencionar el ticket de Plane, o si hay duda sobre a qué proyecto corresponde, el agente debe preguntar brevemente (ej. *"¿A qué ticket de Omnify u Operaciones asociamos esta rama?"*) antes de crearla.
- **Proyectos Personales / Sin Plane:** Si el contexto es un proyecto personal, de código abierto o no vinculado a Plane, no forzar ticket ID; usar el formato convencional estándar: `{tipo}/{kebab-case-descripcion}`.
