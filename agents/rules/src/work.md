# Protocolo de Trabajo y Gobernanza Corporativa (Work Context)

### Ciclo SDLC en Títulos y Commits:
- Clasifica iniciativas y commits formales en 4 fases canónicas: `[SPIKE]` (diagnóstico/investigación), `[RFC]` (diseño/contrato), `[FEAT/FIX/INFRA]` (desarrollo/devops), `[QA]` (pruebas/validación).

### Convenciones de Ramas Git:
- **Patrón Corporativo:** `{tipo}/{TICKET-ID}-{kebab-case-description}` (ej. `feat/OMNIFY-175-campaign-validations`, `fix/OPS-44-mitigate-n8n`).
  - Tipos válidos: `spike`, `feat`, `fix`, `refactor`, `test`, `infra`. Prefijo por defecto: `OMNIFY-`.
- **Iniciativas Multi-Repo:** Si la tarea cruza 2 o más repositorios, activa y utiliza la skill `alo-ws` (`~/.agents/skills/alo-ws/SKILL.md`) operando vía `alo ws`.
- **Ambigüedad:** Si no se especifica un ticket para trabajo corporativo, consulta con el usuario antes de crear la rama.

### Determinación de Ámbito (Corporativo vs Local):
- **Ámbito Corporativo (Plane / Tracker Obligatorio):**
  - Aplica cuando el workspace actual corresponde a repositorios corporativos o cuando el usuario menciona explícitamente tickets con clave (`[A-Z]+-[0-9]+`), "Plane" o "sprint".
  - *Ejecución:* Consulta y opera a través del CLI nativo de `allostasis` (`alo`). Para comandos de telemetría, estándares de living tickets y reglas de paraguas semanales (`OPS`), consulta `~/.agents/skills/alo/SKILL.md`.
  - *Cierre de Hito/Sesión:* Al completar una tarea o finalizar la sesión, propón una bitácora concisa vía `alo ticket comment add` y solicita confirmación antes de enviarla.
- **Ámbito Local / Herramientas Internas / Dotfiles:**
  - Aplica en `~/Code/dotfiles`, scripts locales, desarrollo interno de skills en `~/.agents/skills/` y tareas exploratorias aisladas.
  - **REGLA DE AISLAMIENTO:** NUNCA consultes, busques ni crees tickets en Plane para proyectos locales o de tooling interno. El seguimiento se realiza exclusivamente mediante commits atómicos y claros de Git en la rama activa.
