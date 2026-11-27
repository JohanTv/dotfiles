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

# Perfiles de agy (Antigravity CLI). agy no tiene variable de config propia, así que
# cada perfil es un HOME falso en ~/.agy-<nombre>: login e historial quedan por perfil.
# `agy-new <nombre>` crea uno; el perfil por defecto sigue siendo `agy`.
# Se comparte desde el HOME real (enlaces) todo salvo .gemini, y de .gemini solo la config.
_AGY_SHARED_GEMINI=(GEMINI.md bin config)
# Conversaciones/historial compartidos entre perfiles; solo el token OAuth queda por perfil.
_AGY_SHARED_CLI=(settings.json mcp plugin_data conversations brain annotations history.jsonl conversation_summaries.db jetbox_summaries_proto.pb)

_agy_profile_define() {
  local dir=~/.agy-$1
  eval "agy-$1() { HOME=${(q)dir} agy \"\$@\" }"
}

agy-new() {
  [[ $1 =~ '^[a-z0-9-]+$' ]] || { echo "uso: agy-new <nombre> (a-z, 0-9, -)"; return 1 }
  local dir=~/.agy-$1 f
  [[ -e $dir ]] && { echo "ya existe: $dir"; return 1 }
  mkdir -p $dir/.gemini/antigravity-cli
  # ponytail: snapshot al crear; entradas nuevas en ~ no aparecen, re-enlazar a mano si hace falta
  for f in ~/*(DN); do
    [[ ${f:t} == (.gemini|.agy-*) ]] && continue
    ln -s $f $dir/${f:t}
  done
  for f in $_AGY_SHARED_GEMINI; do
    [[ -e ~/.gemini/$f ]] && ln -s ~/.gemini/$f $dir/.gemini/$f
  done
  for f in $_AGY_SHARED_CLI; do
    [[ -e ~/.gemini/antigravity-cli/$f ]] && ln -s ~/.gemini/antigravity-cli/$f $dir/.gemini/antigravity-cli/$f
  done
  _agy_profile_define $1
  echo "listo: agy-$1 (primera vez: iniciar sesión dentro de agy)"
}

for _d in ~/.agy-*(/N); do _agy_profile_define ${_d:t:s/.agy-/}; done
unset _d
