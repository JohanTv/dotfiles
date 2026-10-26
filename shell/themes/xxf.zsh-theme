# Copy and self modified from ys.zsh-theme, the one of default themes in master repository
# Clean, simple, compatible and meaningful.
# Tested on Linux, Unix and Windows under ANSI colors.
# It is recommended to use with a dark background and the font Inconsolata.
# Colors: black, red, green, yellow, *blue, magenta, cyan, and white.
# http://xiaofan.at
# 2 Jul 2015 - Xiaofan

# Machine name.
local BOX_NAME
if [ -f ~/.box-name ]; then
    BOX_NAME=$(cat ~/.box-name)
else
    BOX_NAME=$HOST
fi

# Directory info.
local current_dir='${PWD/#$HOME/~}'

# VCS
YS_VCS_PROMPT_PREFIX1="%{$fg[white]%}on%{$reset_color%} "
YS_VCS_PROMPT_PREFIX2=":%{$fg[cyan]%}"
YS_VCS_PROMPT_SUFFIX="%{$reset_color%} "
YS_VCS_PROMPT_DIRTY=" %{$fg[red]%}✗"
YS_VCS_PROMPT_CLEAN=" %{$fg[green]%}✔︎"

# Git info.
local git_info='$(git_prompt_info)'
ZSH_THEME_GIT_PROMPT_PREFIX="${YS_VCS_PROMPT_PREFIX1}git${YS_VCS_PROMPT_PREFIX2}"
ZSH_THEME_GIT_PROMPT_SUFFIX="$YS_VCS_PROMPT_SUFFIX"
ZSH_THEME_GIT_PROMPT_DIRTY="$YS_VCS_PROMPT_DIRTY"
ZSH_THEME_GIT_PROMPT_CLEAN="$YS_VCS_PROMPT_CLEAN"

function git_short_hash {
    local dir="$PWD"
    while [[ "$dir" != "/" && -n "$dir" ]]; do
        if [[ -e "$dir/.git" ]]; then
            local hash=$(git rev-parse --short HEAD 2> /dev/null)
            if [[ -n "$hash" ]]; then
                echo -n "%{$fg[white]%}@%{$fg[blue]%}${hash}%{$reset_color%}"
            fi
            return 0
        fi
        dir="${dir:h}"
    done
}
local git_hash='$(git_short_hash)'

# Prompt format: \n # TIME USER at MACHINE in [DIRECTORY] on git:BRANCH STATE \n $ 
PROMPT="
%{$fg[cyan]%}%n \
%{$fg[white]%}at \
%{$fg[green]%}${BOX_NAME} \
%{$fg[white]%}in \
%{$terminfo[bold]$fg[yellow]%}[${current_dir}]%{$reset_color%} \
${git_info}${git_hash} \

%{$fg[red]%}%* \
%{$terminfo[bold]$fg[white]%}› %{$reset_color%}"

if [[ "$USER" == "root" ]]; then
PROMPT="
%{$fg[red]%}%* \
%{$terminfo[bold]$fg[blue]%}#%{$reset_color%} \
%{$bg[yellow]%}%{$fg[cyan]%}%n%{$reset_color%} \
%{$fg[white]%}at \
%{$fg[green]%}${BOX_NAME} \
%{$fg[white]%}in \
%{$terminfo[bold]$fg[yellow]%}[${current_dir}]%{$reset_color%}\
${git_info}${git_hash}
%{$terminfo[bold]$fg[red]%}$ %{$reset_color%}"
fi
