# Protocolo de Trabajo y Determinación de Ámbito

### 1. Ámbito Local / Personal / Tooling Interno:
- **Cuándo aplica:** En `~/Code/dotfiles`, scripts locales, desarrollo interno de skills en `~/.agents/skills/` y proyectos personales/open-source aislados.
- **Aislamiento Estricto:** NUNCA consultes, busques ni crees tickets en Plane para proyectos locales. El seguimiento se realiza exclusivamente mediante commits atómicos y claros de Git en la rama activa.

### 2. Ámbito Corporativo (Plane Tracker):
- **Cuándo aplica:** En repositorios corporativos de la organización o cuando el usuario mencione tickets con clave (`[A-Z]+-[0-9]+`), "Plane" o "sprint".
- **Procedimiento Bajo Demanda:** Consulta y opera mediante la habilidad `alo`:
  - Runbook y gobernanza: `~/.agents/skills/alo/SKILL.md`.
  - Iniciativas multi-repo: opera mediante worktrees vía `alo ws`.
  - Cierre de sesión/hito: propón bitácora concisa con `alo ticket comment add` y solicita confirmación antes de enviarla.
