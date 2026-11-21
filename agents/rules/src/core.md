# Directrices de Operación CLI y Edición de Código

### Comunicación:
- **Idioma del Usuario:** Comunícate siempre en **español** (tono conversacional, técnico y conciso) a menos que se te indique explícitamente lo contrario.

### Edición y Manipulación de Archivos:
- **Sustituciones en Terminal (`sd`):** Para reemplazos regex o masivos en terminal, usa exclusivamente `sd` (`sd 'patrón' 'reemplazo' archivo`). Queda prohibido el uso de `sed -i`, `awk` o `perl -pi` para editar archivos en disco.
- **Libertad de Herramientas:** Utiliza las herramientas nativas de edición (`edit_file`, etc.) o scripts auxiliares (ej. Python) según resulte más limpio, seguro y determinista para la tarea.

### Integridad de Interfaces y Prohibición de Tool Escape:
- **Principio de Caja Negra:** Queda prohibido el acceso directo mediante clientes ad-hoc (`sqlite3`, `duckdb`, `psql`, etc.) a bases de datos internas, cachés locales (`~/.cache/*`) o archivos de estado privado de las herramientas del sistema, salvo instrucción explícita del usuario.
- **Manejo Determinista de Fallos:** Si un CLI o API falla o experimenta timeout, detén la ejecución y reporta el error con transparencia técnica; nunca intentes compensarlo con ingeniería inversa o scraping de bajo nivel.

### Herramientas de Inspección y Búsqueda:
- **Búsqueda de Código:** Usa siempre `rg` (`-S` smart-case, `-n` números de línea, `--max-columns 300`, `--max-count 50`, excluir lockfiles `-g '!*.lock' -g '!package-lock.json'`).
- **Búsqueda de Archivos:** Usa exclusivamente `fd` (`fd -t f`, `fd -t d`). Nunca uses `find`.
- **JSON:** Usa `jq` para extraer propiedades específicas; nunca vuelques payloads JSON completos al contexto.
- **Git:** Formatos compactos (`git status -s`, `git diff --stat`, `git log --oneline -n 5`). Commits convencionales en **inglés**, 1 línea, estrictamente sin firmas de co-autoría ni menciones de IA. `git push` solo bajo orden explícita.
- **Seguridad:** Respeta `.gitignore`. En búsquedas desde `$HOME`, excluye cachés pesadas (`-E ".cache" -E ".bun" -E ".npm" -E ".cargo"`). Nunca inspecciones `.env` con secretos reales (solo `.env.example`).

### Habilidades Especializadas Bajo Demanda:
Antes de ejecutar procedimientos complejos en herramientas del entorno, consulta su runbook en `~/.agents/skills/<name>/SKILL.md`:
- `alo`: Operación de tickets en Plane, cambio de estados, registro de horas y worktrees Git (`alo ws`).
- `go-cli-tui`: Arquitectura hexagonal, diseño SOLID, modo headless M2M y SQLite en Go.
- `dotfiles-sync`: Diagnóstico y auditoría de symlinks del sistema con `dotfiles-doctor`.
- `find-session`: Localización y reanudación de sesiones previas en Gemini, Claude o OpenCode.
