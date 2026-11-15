# Catálogo de Habilidades y Procedimientos del Sistema (Skills Index)

Cuando una tarea coincida con el dominio de una habilidad disponible en `~/.agents/skills/`, el agente DEBE leer las instrucciones detalladas del archivo correspondiente antes de ejecutar acciones complejas.

| Habilidad (Skill) | Cuándo Activar (Triggers de Contexto) | Ruta del Procedimiento (Leer bajo demanda) |
| :--- | :--- | :--- |
| **`plane-tracker` / `allostasis`** | Operación de tickets, cambio de estados, registro de horas/bitácoras o consulta de sprint/agenda corporativa. | `~/.agents/skills/plane-tracker/SKILL.md` |
| **`plane-worktree`** | Tareas que involucren 2 o más repositorios Git simultáneos asociados a un ticket corporativo. | `~/.agents/skills/plane-worktree/SKILL.md` |
| **`go-cli-tui`** | Diseño, arquitectura SOLID, dual-mode (headless IA vs Charm TUI), SQLite o pruebas de herramientas CLI en Go. | `~/.agents/skills/go-cli-tui/SKILL.md` |
| **`dotfiles-sync`** | Diagnóstico de configuración del sistema, verificación de symlinks, auditoría con `dotfiles-doctor` o actualización de dotfiles. | `~/.agents/skills/dotfiles-sync/SKILL.md` |
| **`find-session`** | Búsqueda o reanudación de sesiones y conversaciones anteriores de Claude Code, Gemini CLI o OpenCode. | `~/.agents/skills/find-session/SKILL.md` |
| **`wmctrl-focus`** | Creación y configuración de atajos de teclado para enfocar ventanas en Ubuntu Linux (GNOME X11). | `~/.agents/skills/desktop-linux/wmctrl-focus/SKILL.md` |

*Instrucción de Ejecución:* Si el usuario solicita una acción cubierta por este catálogo, inspecciona el archivo `SKILL.md` indicado antes de inventar comandos o suponer parámetros.
