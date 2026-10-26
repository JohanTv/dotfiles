# Ecosistema de Agentes de IA (Gobernanza y Catálogo)

Este directorio centraliza las directrices, reglas de comportamiento y habilidades procedurales (*skills*) para todos los agentes de codificación del entorno (**Gemini CLI / `agy`**, **Claude Code** y **OpenCode**).

---

## 1. Reglas Globales Inyectadas (`rules/`)

Directrices invariantes inyectadas permanentemente en el *system prompt* de cada sesión. Diseñadas para consumir el mínimo de tokens (~250 tokens) y garantizar máxima eficiencia operativa.

| Archivo Fuente | Destino en Sistema | Propósito |
| :--- | :--- | :--- |
| [`rules/global-rules.md`](file:///home/johantv/Code/dotfiles/agents/rules/global-rules.md) | `~/.gemini/GEMINI.md`<br>`~/.claude/CLAUDE.md`<br>`~/.config/opencode/AGENTS.md` | Búsqueda (`rg`, `fd`, `jq`, `sd`), Commits estándar en inglés sin co-autor, exclusión de cachés y seguridad `.env`. |

---

## 2. Catálogo de Habilidades Reutilizables (`skills/`)

Procedimientos estandarizados (*runbooks*) que los agentes cargan **bajo demanda** únicamente cuando la tarea lo requiere, sin saturar la ventana de contexto.

| Skill | Compatibilidad | Ubicación | Descripción | Scripts asociados |
| :--- | :---: | :--- | :--- | :--- |
| **`find-session`** | 🌐 Universal<br>*(WSL + Ubuntu)* | [`skills/find-session/SKILL.md`](file:///home/johantv/Code/dotfiles/agents/skills/find-session/SKILL.md) | Localización instantánea de IDs de conversaciones previas en Gemini, Claude Code y OpenCode. | [`bin/common/find-session`](file:///home/johantv/Code/dotfiles/bin/common/find-session) |
| **`wmctrl-focus`** | 🐧 Desktop Linux<br>*(Ubuntu GNOME X11)* | [`skills/wmctrl-focus/SKILL.md`](file:///home/johantv/Code/dotfiles/agents/skills/wmctrl-focus/SKILL.md) | Procedimiento estándar para crear atajos de enfoque de ventanas con `wmctrl`. | [`bin/desktop-linux/focus-alacritty`](file:///home/johantv/Code/dotfiles/bin/desktop-linux/focus-alacritty)<br>[`bin/desktop-linux/focus-nautilus`](file:///home/johantv/Code/dotfiles/bin/desktop-linux/focus-nautilus) |

---

## 3. Servidores MCP Globales (`mcp/`)

Integraciones del protocolo Model Context Protocol (MCP) disponibles globalmente para los tres asistentes:

| Servidor MCP | Comando / Transporte | Asistentes Compatibles | Propósito |
| :--- | :--- | :--- | :--- |
| **`chrome-devtools`** | `npx -y chrome-devtools-mcp` | Gemini CLI (`agy`)<br>Claude Code<br>OpenCode | Automatización de navegador, inspección de DOM, toma de capturas y depuración web en vivo. |

* **Gemini:** Configurado en `~/.gemini/config/mcp_config.json` (fusionado desde [`mcp/gemini_mcp.json`](file:///home/johantv/Code/dotfiles/agents/mcp/gemini_mcp.json)).
* **OpenCode:** Configurado en `~/.config/opencode/opencode.json` (enlazado a [`mcp/opencode.json`](file:///home/johantv/Code/dotfiles/agents/mcp/opencode.json)).
* **Claude Code:** Registrado en el ámbito de usuario en `~/.claude.json`.

---

## 4. Directrices para Añadir Nuevas Capacidades

1. **Nuevas Reglas de Comportamiento:** Si es una regla que debe aplicar en cada turno, debe ser concisa (menos de 5 líneas) y agregarse a [`rules/global-rules.md`](file:///home/johantv/Code/dotfiles/agents/rules/global-rules.md).
2. **Nuevos Procedimientos o Flujos:** Si es un procedimiento de varios pasos (ej. despliegues, Docker, testing complejo), crea una carpeta en `skills/<nombre>/SKILL.md` con frontmatter YAML estándar.
3. **Scripts Ejecutables:** Si la skill requiere un script de apoyo:
   * Colócalo en `bin/common/` si corre tanto en Linux nativo como en WSL.
   * Colócalo en `bin/desktop-linux/` si requiere dependencias gráficas de GNOME/X11.
