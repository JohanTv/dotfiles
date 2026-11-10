# Perfiles de Claude Code. `work` vive en ~/.claude; el resto en ~/.claude-<nombre>.
# Cada perfil expone `claude-<nombre>`; `claude-new <nombre>` crea uno nuevo.

# Se comparte desde ~/.claude (enlaces); login, historial y memoria quedan por perfil.
_CLAUDE_SHARED=(CLAUDE.md settings.json keybindings.json skills plugins)

_claude_profile_define() {
  local dir=~/.claude-$1
  [[ $1 == work ]] && dir=~/.claude
  eval "claude-$1() { CLAUDE_CONFIG_DIR=${(q)dir} claude \"\$@\" }"
}

claude-new() {
  [[ $1 =~ '^[a-z0-9-]+$' && $1 != work ]] || { echo "uso: claude-new <nombre> (a-z, 0-9, -)"; return 1 }
  local dir=~/.claude-$1 f
  [[ -e $dir ]] && { echo "ya existe: $dir"; return 1 }
  mkdir -p $dir
  for f in $_CLAUDE_SHARED; do
    [[ -e ~/.claude/$f ]] && ln -s ~/.claude/$f $dir/$f
  done
  _claude_profile_define $1
  echo "listo: claude-$1 (primera vez: /login)"
}

_claude_profile_define work
for _d in ~/.claude-*(/N); do _claude_profile_define ${_d:t:s/.claude-/}; done
unset _d
