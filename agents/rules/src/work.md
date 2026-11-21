# Protocolo de Trabajo y Determinación de Ámbito

### 1. Ámbito Local / Personal / Tooling Interno:
- **Cuándo aplica:** En `~/Code/dotfiles`, scripts locales, skills en `~/.agents/skills/` y proyectos personales/open-source aislados (incluyendo `alo`).
- **Seguimiento Soberano en Git:** El backlog y tareas locales se gestionan exclusivamente vía Git. Prohibido crear tickets en Plane para gestionar estos repositorios.
- **Pruebas de Integración:** En herramientas conectadas (ej. `alo`), se permite probar contra Plane bajo autorización o para validar flujos reales, limpiando datos de prueba.

### 2. Ámbito Corporativo (Plane Tracker):
- **Cuándo aplica:** En repositorios corporativos de la organización o al citar tickets (`[A-Z]+-[0-9]+`), "Plane" o "sprint".
- **Procedimiento Bajo Demanda:** Opera vía habilidad `alo` (`~/.agents/skills/alo/SKILL.md`). Propón bitácora con `alo ticket comment add` al cerrar hitos.
