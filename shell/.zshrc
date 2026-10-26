# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# If you come from bash you might have to change your $PATH.
# export PATH=$HOME/bin:$HOME/.local/bin:/usr/local/bin:$PATH

# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time Oh My Zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/ohmyzsh/ohmyzsh/wiki/Themes
ZSH_THEME="xxf"

# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in $ZSH/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment one of the following lines to change the auto-update behavior
# zstyle ':omz:update' mode disabled  # disable automatic updates
# zstyle ':omz:update' mode auto      # update automatically without asking
# zstyle ':omz:update' mode reminder  # just remind me to update when it's time

# Uncomment the following line to change how often to auto-update (in days).
# zstyle ':omz:update' frequency 13

# Uncomment the following line if pasting URLs and other text is messed up.
# DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# You can also set it to another string to have that shown instead of the default red dots.
# e.g. COMPLETION_WAITING_DOTS="%F{yellow}waiting...%f"
# Caution: this setting can cause issues with multiline prompts in zsh < 5.7.1 (see #5765)
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load?
# Standard plugins can be found in $ZSH/plugins/
# Custom plugins may be added to $ZSH_CUSTOM/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
# Homebrew environment (configuración estática para evitar forks y subprocesos al iniciar)
if [[ -d "/home/linuxbrew/.linuxbrew" ]]; then
  export HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew"
  export HOMEBREW_CELLAR="/home/linuxbrew/.linuxbrew/Cellar"
  export HOMEBREW_REPOSITORY="/home/linuxbrew/.linuxbrew/Homebrew"
  export PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin${PATH+:$PATH}"
  [ -z "${MANPATH-}" ] || export MANPATH="${MANPATH%"${MANPATH##*[!:]}"}::"
  export INFOPATH="/home/linuxbrew/.linuxbrew/share/info:${INFOPATH:-}"
fi

plugins=(git ssh-agent zoxide fzf zsh-autosuggestions)

# Optimización: acelerar compinit usando caché (-C) si el archivo de volcado tiene menos de 24 horas
autoload -Uz compinit
compinit() {
  unfunction compinit
  autoload -Uz compinit
  setopt local_options extended_glob
  local dump="$3"
  if [[ -n "$dump" && -f "$dump" && -n "$dump"(#qN.mh+24) ]]; then
    compinit "$@"
  else
    compinit -C "$@"
  fi
}

source $ZSH/oh-my-zsh.sh

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='nvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch $(uname -m)"

# Set personal aliases, overriding those provided by Oh My Zsh libs,
# plugins, and themes. Aliases can be placed here, though Oh My Zsh
# users are encouraged to define aliases within a top-level file in
# the $ZSH_CUSTOM folder, with .zsh extension. Examples:
# - $ZSH_CUSTOM/aliases.zsh
# - $ZSH_CUSTOM/macos.zsh
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"

# source ~/.local/share/omakub/defaults/bash/rc
[[ -f "$HOME/.local/share/omakub/defaults/bash/functions" ]] && source "$HOME/.local/share/omakub/defaults/bash/functions"

alias p3="python3"
alias bat='batcat'
alias lzg='lazygit'
alias lzd='lazydocker'

alias ls='eza -lh --group-directories-first --icons=auto'
alias lsa='ls -a'
alias lt='eza --tree --level=2 --long --icons --git'
alias lta='lt -a'

alias ff="fzf --preview 'batcat --style=numbers --color=always {}'"
command -v fdfind >/dev/null 2>&1 && alias fd='fdfind'
alias v='nvim'
alias open='xdg-open'
alias zj="zellij"
alias zja="zellij attach"
alias zjls="zellij list-sessions"
# alias ag='antigravity --ignore-gpu-blacklist --enable-gpu-rasterization --enable-zero-copy --disable-gpu-driver-bug-workarounds --enable-native-gpu-memory-buffers'
ag() {
    antigravity "$@" --ignore-gpu-blacklist --enable-gpu-rasterization --enable-zero-copy --disable-gpu-driver-bug-workarounds --enable-native-gpu-memory-buffers
}
# bun completions
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

export NVM_DIR="$HOME/.nvm"
# Añadir la versión predeterminada de Node directamente al PATH (acceso inmediato sin demora)
[ -d "$NVM_DIR/versions/node/v24.12.0/bin" ] && export PATH="$NVM_DIR/versions/node/v24.12.0/bin:$PATH"

# Lazy-load NVM solo cuando se ejecute explícitamente el comando 'nvm'
nvm() {
  unset -f nvm
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
  nvm "$@"
}




# Added by Antigravity CLI installer
export PATH="$HOME/.local/bin:$PATH"

# Antigravity CLI auto-approve permissions
alias agy="agy --dangerously-skip-permissions"

# Cargar secretos y configuraciones locales privadas si existen
[[ -f "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

# Auto-iniciar o adjuntar sesión de Zellij en shells interactivos
if [[ -o interactive ]] && [[ -z "$ZELLIJ" ]] && [[ "${ZELLIJ_AUTO_START:-true}" == "true" ]] && [[ "$TERM" != "dumb" ]] && command -v zellij >/dev/null 2>&1; then
  # Evitar anidar en la terminal integrada de VS Code / Antigravity IDE a menos que se configure explícitamente
  if [[ "$TERM_PROGRAM" != "vscode" || "${ZELLIJ_AUTO_START_IDE:-false}" == "true" ]]; then
    if [[ "${ZELLIJ_AUTO_ATTACH:-true}" == "true" ]]; then
      zellij attach -c
    else
      zellij
    fi

    if [[ "${ZELLIJ_AUTO_EXIT:-true}" == "true" ]]; then
      exit
    fi
  fi
fi
