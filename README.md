# 🛠️ Johan's Workstation (Dotfiles)

> **Reproducible Linux (Ubuntu Native), WSL & AI Agents Setup.**  
> Configuración integral como código (*Infrastructure-as-Code*) para terminal, multiplexores, scripts de productividad y orquestación unificada de agentes de IA.

---

## 📌 Aspectos Destacados

* **🤖 Orquestación de Agentes de IA:** Reglas operativas optimizadas en tokens (~250 tokens), catálogo de skills bajo demanda y servidores MCP globales compartidos entre **Gemini CLI (`agy`)**, **Claude Code** y **OpenCode**.
* **⚡ Ecosistema de Terminal Moderno:** **Alacritty** (acelerado por GPU) + **Zellij** (multiplexor Rust) configurados para máxima velocidad.
* **🐧 Híbrido Ubuntu & WSL:** Detección automática del entorno; aprovisiona herramientas de escritorio en Linux nativo y omite dependencias gráficas en WSL.
* **🔒 Seguridad por Diseño:** Manejo estricto de secretos mediante el patrón `~/.zshrc.local` (ignorado en Git).
* **🎯 Scripts de Productividad:** Búsqueda instantánea de sesiones de IA (`find-session` en Gemini, Claude y OpenCode), control de foco con `wmctrl`, y herramientas CLI modernas (`rg`, `fd`, `jq`, `sd`).

---

## 📂 Arquitectura del Repositorio

```text
dotfiles/
├── Makefile                    # 🎯 Orquestador maestro (make, make work, make personal, make doctor)
├── install.sh                  # Instalador idempotente y detector de SO
├── .gitignore                  # Protección contra secretos, dist/ y temporales
│
├── agents/                     # 🤖 Orquestación unificada de Agentes de IA
│   ├── AGENTS.md               # Catálogo maestro y gobernanza de agentes
│   ├── rules/                  # Reglas de comportamiento inyectadas por turno
│   │   ├── src/                # Fuentes modulares (core.md, work.md, personal.md)
│   │   └── dist/               # Artefacto activo compilado (active-rules.md, readonly)
│   ├── skills/                 # Procedimientos y runbooks bajo demanda
│   │   ├── common/             # Skills universales (find-session, dotfiles-sync)
│   │   ├── desktop-linux/      # Skills exclusivas GNOME/X11 (wmctrl-focus)
│   │   └── work/               # Skills de trabajo empresarial (plane-tracker)
│   └── mcp/                    # Servidores Model Context Protocol (MCP)
│       ├── gemini_mcp.json     # Integración global para Gemini CLI (agy)
│       └── opencode.json       # Configuración global y MCP para OpenCode
│
├── terminal/                   # 🖥️ Configuración de emuladores y multiplexores
│   ├── alacritty/              # Configuración modular (fuentes, temas, atajos)
│   └── zellij/                 # Layouts y keybindings de Zellij
│
├── shell/                      # 🐚 Entorno de línea de comandos
│   ├── .zshrc                  # Configuración optimizada de Zsh (carga tema xxf)
│   ├── .zshrc.local.example    # Plantilla para secretos y variables de Plane
│   └── themes/                 # Temas personalizados de Oh My Zsh
│       └── xxf.zsh-theme       # Tema propio modificado (branch status, host, etc.)
│
└── bin/                        # 🚀 Utilidades y automatizaciones
    ├── common/                 # Scripts universales (WSL + Ubuntu): find-session, dotfiles-doctor
    └── desktop-linux/          # Scripts específicos de GNOME/X11: focus-alacritty, etc.
```

---

## 🚀 Instalación Rápida

En cualquier máquina nueva con Ubuntu o WSL (puedes clonarlo en `~/Code/dotfiles`, `~/.dotfiles` o la ruta que prefieras; el instalador y las herramientas son 100% agnósticos):

```bash
git clone https://github.com/johantv/dotfiles.git ~/Code/dotfiles
cd ~/Code/dotfiles
./install.sh
```

El script `install.sh`:
1. Crea enlaces simbólicos (*symlinks*) limpios a tu `$HOME`.
2. Respalda automáticamente cualquier configuración preexistente con sufijo `.bak`.
3. Detecta si estás en WSL o Ubuntu nativo para enlazar solo lo que corresponde.

---

## 🔒 Variables y Secretos Locales

Para añadir API keys, tokens o alias privados sin subirlos a GitHub:

```bash
cp shell/.zshrc.local.example ~/.zshrc.local
# Edita ~/.zshrc.local con tus tokens privados
```
El archivo `~/.zshrc.local` se cargará automáticamente al iniciar tu shell y está excluido de Git.

---

## 📜 Licencia

MIT © [Johan](https://github.com/johantv)
