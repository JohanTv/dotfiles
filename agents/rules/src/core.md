# Directrices de Operación CLI y Código

- **Idioma:** Español técnico y conciso, salvo instrucción contraria.
- **Edición:** En vez de usar `sed`, `awk` o `perl`, usa `sd`.
- **DBs y Estado Interno:** Prohibido alterar DBs para puentear fallos de CLIs/APIs. Consultas directas (`sqlite3`, `psql`) permitidas para auditoría o diagnóstico bajo autorización, en solo lectura y sin exponer credenciales.
- **Inspección:** Código con `rg` (`-S`, `-n`, excluir lockfiles), archivos con `fd` (nunca `find`), JSON con `jq` (propiedades específicas). Excluye cachés en `$HOME` (`.cache`, `.bun`, `.cargo`) y jamás inspecciones secretos en `.env`.
- **Git:** Formato compacto (`git status -s`, `git diff --stat`). Prohibido commitear de forma autónoma; commits solo bajo orden explícita o confirmación previa (convencionales en inglés, 1 línea, sin atribución a IA). `git push` solo bajo orden explícita.
- **Skills bajo demanda:** Antes de tareas complejas en herramientas del entorno, consulta su runbook en `~/.agents/skills/<name>/SKILL.md` (`alo`, `go-cli-tui`, `dotfiles-sync`, `find-session`, `context-economist`).
