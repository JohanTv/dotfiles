#!/usr/bin/env bash
# ==============================================================================
# Johan's Workstation Setup & Dotfiles Installer
# Idempotent installer for Ubuntu & WSL environments.
# ==============================================================================

set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SUFFIX=".bak_$(date +%Y%m%d_%H%M%S)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }

link_file() {
    local src="$1"
    local dest="$2"

    if [[ ! -e "$src" && ! -L "$src" ]]; then
        log_warn "Origen no encontrado en dotfiles: $src"
        return 1
    fi

    mkdir -p "$(dirname "$dest")"

    # If already correctly symlinked, do nothing
    if [[ -L "$dest" && "$(readlink -f "$dest")" == "$(readlink -f "$src")" ]]; then
        log_ok "Ya enlazado: $dest"
        return 0
    fi

    # If exists and is not our symlink, backup
    if [[ -e "$dest" || -L "$dest" ]]; then
        log_warn "Respaldando existente: $dest -> $dest$BACKUP_SUFFIX"
        mv "$dest" "$dest$BACKUP_SUFFIX"
    fi

    ln -sf "$src" "$dest"
    log_ok "Enlazado: $dest -> $src"
}

# ------------------------------------------------------------------------------
# 1. Detectar Entorno (WSL vs Ubuntu Nativo)
# ------------------------------------------------------------------------------
IS_WSL=false
if grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    IS_WSL=true
    log_info "Entorno detectado: Windows Subsystem for Linux (WSL)"
else
    log_info "Entorno detectado: Linux Nativo (Ubuntu/GNOME)"
fi

# ------------------------------------------------------------------------------
# 1b. Herramientas base (opt-in con --tools; idempotente)
# apt: lo que el .zshrc asume (batcat/fdfind) + openssh-client. brew: ver Brewfile.
# ------------------------------------------------------------------------------
INSTALL_TOOLS=false
for arg in "$@"; do
    case "$arg" in
        --tools) INSTALL_TOOLS=true ;;
        -h|--help) echo "Uso: ./install.sh [--tools]"; exit 0 ;;
        *) log_warn "Argumento desconocido: $arg" ;;
    esac
done

APT_BASE=(openssh-client curl git unzip build-essential procps file jq fd-find bat fzf zoxide eza zsh gh tree btop)
BREW_BIN="/home/linuxbrew/.linuxbrew/bin/brew"

install_tools() {
    local missing=()
    for p in "${APT_BASE[@]}"; do
        dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
    done
    if (( ${#missing[@]} )); then
        log_info "Instalando paquetes apt: ${missing[*]}"
        sudo apt-get update -y && sudo apt-get install -y "${missing[@]}"
    else
        log_ok "Paquetes apt base ya instalados"
    fi

    if ! command -v brew >/dev/null 2>&1 && [[ ! -x "$BREW_BIN" ]]; then
        log_info "Instalando Homebrew..."
        NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        log_ok "Homebrew ya instalado"
    fi
    # Solo para esta ejecución; el .zshrc ya exporta el PATH de brew
    [[ -x "$BREW_BIN" ]] && eval "$("$BREW_BIN" shellenv)"

    if command -v brew >/dev/null 2>&1; then
        HOMEBREW_NO_ANALYTICS=1 brew bundle --file="$DOTFILES_DIR/Brewfile"
    fi

    # zsh como shell de login (lee /etc/passwd: $SHELL no refleja el cambio hasta reloguear)
    local login_shell zsh_path
    login_shell="$(getent passwd "$USER" | cut -d: -f7)"
    zsh_path="$(command -v zsh || true)"
    if [[ -n "$zsh_path" && "$login_shell" != "$zsh_path" ]]; then
        log_info "Cambiando shell de login a zsh (efectivo al reabrir sesión)..."
        sudo chsh -s "$zsh_path" "$USER"
    else
        log_ok "zsh ya es el shell de login"
    fi

    # oh-my-zsh sin tocar ~/.zshrc (el .zshrc del repo se enlaza en la sección 5)
    if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
        log_info "Instalando oh-my-zsh..."
        RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
    else
        log_ok "oh-my-zsh ya instalado"
    fi

    local autosuggest_dir="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions"
    if [[ ! -d "$autosuggest_dir" ]]; then
        log_info "Instalando plugin zsh-autosuggestions..."
        git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions "$autosuggest_dir"
    else
        log_ok "zsh-autosuggestions ya instalado"
    fi

    if ! command -v bun >/dev/null 2>&1 && [[ ! -x "$HOME/.bun/bin/bun" ]]; then
        log_info "Instalando bun..."
        curl -fsSL https://bun.com/install | bash
    else
        log_ok "bun ya instalado"
    fi
}

if [[ "$INSTALL_TOOLS" == true ]]; then
    install_tools
else
    for t in ssh jq rg sd lazygit zellij gh tree btop zsh; do
        command -v "$t" >/dev/null 2>&1 || log_warn "Falta '$t' (ejecuta ./install.sh --tools)"
    done
    command -v bun >/dev/null 2>&1 || [[ -x "$HOME/.bun/bin/bun" ]] || log_warn "Falta 'bun' (ejecuta ./install.sh --tools)"
    [[ -d "$HOME/.oh-my-zsh" ]] || log_warn "Falta oh-my-zsh (ejecuta ./install.sh --tools)"
    command -v fd >/dev/null 2>&1 || command -v fdfind >/dev/null 2>&1 || log_warn "Falta 'fd' (ejecuta ./install.sh --tools)"
fi

# ------------------------------------------------------------------------------
# 2. Configurar y Compilar Reglas y Skills de Agentes IA (via Makefile)
# ------------------------------------------------------------------------------
log_info "Configurando y compilando reglas y skills de Agentes IA..."
make -C "$DOTFILES_DIR" all

# ------------------------------------------------------------------------------
# 3. Configurar Servidores MCP Globales (Chrome DevTools)
# ------------------------------------------------------------------------------
log_info "Configurando servidores MCP globales (Chrome DevTools)..."

link_file "$DOTFILES_DIR/agents/mcp/opencode.json" "$HOME/.config/opencode/opencode.json"

if command -v jq >/dev/null 2>&1; then
    # Gemini CLI (~/.gemini/config/mcp_config.json requiere fusión con jq para preservar servidores locales)
    mkdir -p "$HOME/.gemini/config"
    [[ ! -f "$HOME/.gemini/config/mcp_config.json" ]] && echo '{"mcpServers":{}}' > "$HOME/.gemini/config/mcp_config.json"
    tmp_gemini=$(mktemp)
    jq -s '.[0] * .[1]' "$HOME/.gemini/config/mcp_config.json" "$DOTFILES_DIR/agents/mcp/gemini_mcp.json" > "$tmp_gemini" && mv "$tmp_gemini" "$HOME/.gemini/config/mcp_config.json"
    log_ok "chrome-devtools MCP registrado en ~/.gemini/config/mcp_config.json"

    # Claude Code (~/.claude.json requiere fusión con jq para preservar estado local)
    if [[ -f "$HOME/.claude.json" ]]; then
        tmp_claude=$(mktemp)
        jq '.mcpServers["chrome-devtools"] = {"type": "stdio", "command": "npx", "args": ["-y", "chrome-devtools-mcp"], "env": {}}' "$HOME/.claude.json" > "$tmp_claude" && mv "$tmp_claude" "$HOME/.claude.json"
        log_ok "chrome-devtools MCP registrado en ~/.claude.json"
    fi
else
    log_warn "jq no está instalado en el sistema. Se omitió la fusión de mcp_config.json y ~/.claude.json. Instala jq para registrar Chrome DevTools MCP automáticamente."
fi

# ------------------------------------------------------------------------------
# 4. Enlazar Configuraciones de Terminal (Alacritty y Zellij)
# ------------------------------------------------------------------------------
log_info "Configurando Alacritty y Zellij..."
link_file "$DOTFILES_DIR/terminal/alacritty" "$HOME/.config/alacritty"
link_file "$DOTFILES_DIR/terminal/zellij" "$HOME/.config/zellij"

# ------------------------------------------------------------------------------
# 5. Enlazar Configuración de Shell (Zsh y Tema xxf)
# ------------------------------------------------------------------------------
log_info "Configurando Zsh y temas..."
link_file "$DOTFILES_DIR/shell/.zshrc" "$HOME/.zshrc"

# Crear .zshrc.local si no existe
if [[ ! -f "$HOME/.zshrc.local" ]]; then
    cp "$DOTFILES_DIR/shell/.zshrc.local.example" "$HOME/.zshrc.local"
    log_info "Creado ~/.zshrc.local como plantilla para secretos y variables privadas."
fi

# Instalar tema personalizado xxf en Oh My Zsh
zsh_custom="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
if [[ -f "$DOTFILES_DIR/shell/themes/xxf.zsh-theme" ]]; then
    mkdir -p "$zsh_custom/themes"
    link_file "$DOTFILES_DIR/shell/themes/xxf.zsh-theme" "$zsh_custom/themes/xxf.zsh-theme"
    if [[ -d "$HOME/.oh-my-zsh/themes" ]]; then
        link_file "$DOTFILES_DIR/shell/themes/xxf.zsh-theme" "$HOME/.oh-my-zsh/themes/xxf.zsh-theme"
    fi
fi

# ------------------------------------------------------------------------------
# 6. Enlazar Scripts Ejecutables a ~/.local/bin
# ------------------------------------------------------------------------------
log_info "Enlazando scripts ejecutables a ~/.local/bin..."
mkdir -p "$HOME/.local/bin"

# Scripts comunes (corren en WSL y Ubuntu)
for script in "$DOTFILES_DIR"/bin/common/*; do
    if [[ -f "$script" ]]; then
        chmod +x "$script"
        link_file "$script" "$HOME/.local/bin/$(basename "$script")"
    fi
done

# Scripts específicos de escritorio Linux (wmctrl / atajos GNOME)
if [[ "$IS_WSL" == false ]]; then
    log_info "Instalando scripts de escritorio GNOME/X11..."
    for script in "$DOTFILES_DIR"/bin/desktop-linux/*; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            link_file "$script" "$HOME/.local/bin/$(basename "$script")"
        fi
    done
else
    log_info "Omitiendo scripts de escritorio X11/GNOME (modo WSL activo)."
fi

# Scripts exclusivos de WSL (integraciones con Windows)
if [[ "$IS_WSL" == true ]]; then
    log_info "Instalando scripts exclusivos de WSL..."
    for script in "$DOTFILES_DIR"/bin/wsl/*; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            link_file "$script" "$HOME/.local/bin/$(basename "$script")"
        fi
    done
else
    log_info "Omitiendo scripts exclusivos de WSL (Linux nativo)."
fi

# Scripts específicos de perfil de trabajo (Plane / Omnify)
ACTIVE_PROFILE="$(cat "$DOTFILES_DIR/.active-profile" 2>/dev/null || echo "${DOTFILES_PROFILE:-work}")"
if [[ "$ACTIVE_PROFILE" == "work" && -d "$DOTFILES_DIR/bin/work" ]]; then
    log_info "Instalando scripts de trabajo (perfil work activo)..."
    for script in "$DOTFILES_DIR"/bin/work/*; do
        if [[ -f "$script" ]]; then
            chmod +x "$script"
            link_file "$script" "$HOME/.local/bin/$(basename "$script")"
        fi
    done
fi

echo ""
log_ok "¡Instalación completada con éxito!"
log_info "Reinicia tu terminal o ejecuta: source ~/.zshrc"
