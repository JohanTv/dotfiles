# Ecosistema de Agentes de IA (Gobernanza y Catálogo)

Este directorio centraliza las directrices, reglas de comportamiento y habilidades procedurales (*skills*) para todos los agentes de codificación del entorno (**Gemini CLI / `agy`**, **Claude Code** y **OpenCode**).

---

## 1. Arquitectura Modular de Reglas (`rules/`)

El sistema utiliza un patrón de ensamblado modular basado en **perfiles de contexto** (`work` vs `personal`), orquestado mediante el `Makefile` raíz:

```text
agents/rules/
├── src/                          # Fuentes modulares (editas aquí)
│   ├── core.md                   # Invariantes: Búsqueda CLI, Commits en inglés, Seguridad .env
│   ├── work.md                   # Perfil Trabajo: 4 fases (SDLC), tracking Plane y tickets paraguas
│   └── personal.md               # Perfil Personal: Flujo ágil y ligero para proyectos propios
└── dist/                         # Artefacto generado (ignorado en Git, chmod 444)
    └── active-rules.md           # Enlace simbólico activo para los tres asistentes
```

| Archivo Fuente | Perfiles | Destino en Sistema | Propósito |
| :--- | :---: | :--- | :--- |
| `src/core.md` | Todos | `~/.gemini/GEMINI.md`<br>`~/.claude/CLAUDE.md`<br>`~/.config/opencode/AGENTS.md`<br>*(vía `dist/active-rules.md`)* | Herramientas primarias (`rg`, `fd`, `jq`, `sd`), Conventional Commits en inglés sin co-autor, exclusión de cachés y seguridad `.env`. |
| `src/work.md` | `work` | *(mismos destinos)* | Clasificación de tareas en 4 fases (`Spike`, `RFC`, `Dev`, `QA`), uso de la skill `plane-tracker` y tickets paraguas. |
| `src/personal.md` | `personal` | *(mismos destinos)* | Modo personal ligero sin sobrecarga de tracking corporativo. |

---

## 2. Catálogo de Habilidades Reutilizables (`skills/`)

Procedimientos estandarizados (*runbooks*) que los agentes cargan **bajo demanda** únicamente cuando la tarea lo requiere, clasificados por entorno y perfil:

| Skill | Categoría | Compatibilidad | Ubicación | Descripción |
| :--- | :---: | :---: | :--- | :--- |
| **`find-session`** | `common/` | 🌐 Universal<br>*(WSL + Ubuntu)* | [`skills/common/find-session/SKILL.md`](skills/common/find-session/SKILL.md) | Localización instantánea de IDs de conversaciones previas en Gemini, Claude Code y OpenCode. |
| **`dotfiles-sync`** | `common/` | 🌐 Universal<br>*(WSL + Ubuntu)* | [`skills/common/dotfiles-sync/SKILL.md`](skills/common/dotfiles-sync/SKILL.md) | Diagnóstico, auditoría de symlinks y detección de cambios locales con `dotfiles-doctor`. |
| **`wmctrl-focus`** | `desktop-linux/` | 🐧 Desktop Linux<br>*(Ubuntu GNOME X11)* | [`skills/desktop-linux/wmctrl-focus/SKILL.md`](skills/desktop-linux/wmctrl-focus/SKILL.md) | Procedimiento estándar para crear atajos de enfoque de ventanas con `wmctrl`. |
| **`plane-tracker`** | `work/` | 🏢 Solo Perfil Work<br>*(WSL + Ubuntu)* | [`skills/work/plane-tracker/SKILL.md`](skills/work/plane-tracker/SKILL.md) | Registro de bitácoras de sesión, tiempos y entregables en Plane con formato dual-layer. |

---

## 3. Servidores MCP Globales (`mcp/`)

Integraciones del protocolo Model Context Protocol (MCP) disponibles globalmente para los tres asistentes:

| Servidor MCP | Comando / Transporte | Asistentes Compatibles | Propósito |
| :--- | :--- | :--- | :--- |
| **`chrome-devtools`** | `npx -y chrome-devtools-mcp` | Gemini CLI (`agy`)<br>Claude Code<br>OpenCode | Automatización de navegador, inspección de DOM, capturas y depuración web en vivo. |

* **Gemini:** Configurado en `~/.gemini/config/mcp_config.json` (fusionado desde [`mcp/gemini_mcp.json`](mcp/gemini_mcp.json)).
* **OpenCode:** Configurado en `~/.config/opencode/opencode.json` (enlazado a [`mcp/opencode.json`](mcp/opencode.json)).
* **Claude Code:** Registrado en el ámbito de usuario en `~/.claude.json`.

---

## 4. Orquestación mediante Makefile

Para compilar y alternar perfiles:

```bash
make work       # Compila perfil corporativo (core + work) y activa plane-tracker
make personal   # Compila perfil personal (core + personal) y poda plane-tracker
make            # Recompila el perfil activo (.active-profile)
make doctor     # Ejecuta auditoría completa de enlaces e integridad
```
