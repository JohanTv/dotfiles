# Directrices de Operación CLI y Edición de Código

### Comunicación:
- **Idioma del Usuario:** Comunícate siempre en **español** (tono conversacional, técnico y conciso) a menos que se te indique explícitamente lo contrario.

### Jerarquía de Modificación de Archivos (MANDATORIA):
1. **Edición Primaria de Código/Archivos:** Utiliza SIEMPRE las herramientas nativas del agente (`str_replace_editor`, `edit_file`, `patch` o equivalentes de tu entorno). NO invoques shells ni comandos de terminal para editar archivos si tu runtime dispone de una herramienta de edición dedicada.
2. **Sustituciones Batch por CLI (`sd`):** Si requieres sustitución de patrones o regex masivos a través de la terminal:
   - Usa EXCLUSIVAMENTE `sd 'pattern' 'replacement' file`.
   - **REGLA NEGATIVA ESTRICTA:** Queda TERMINANTEMENTE PROHIBIDO el uso de `sed`, `awk` o `perl -pi` para editar archivos en el disco. Cualquier comando `sed -i` es una violación crítica de protocolo.

### Integridad de Interfaces y Prohibición de Tool Escape (MANDATORIA):
- **Principio de Caja Negra:** Queda TERMINANTEMENTE PROHIBIDO el acceso directo mediante clientes ad-hoc (`sqlite3`, `duckdb`, `psql`, `redis-cli`, etc.) a bases de datos internas, cachés locales (`~/.cache/*`) o archivos de estado privado de las herramientas del sistema, salvo instrucción explícita e inequívoca del usuario.
- **Prohibición de Adivinación de Esquemas:** NUNCA ejecutes `.tables`, `.schema` ni queries exploratorios `SELECT` contra bases de datos que pertenezcan al runtime de una aplicación o skill.
- **Manejo Determinista de Fallos:** Si un CLI o API falla, arroja un resultado inesperado o experimenta timeouts:
  - DETÉN inmediatamente la ejecución.
  - REPORTA con transparencia técnica el código de salida, el mensaje de error o la advertencia recibida.
  - NUNCA intentes compensar el fallo haciendo ingeniería inversa o scraping de bajo nivel por terminal.

### Herramientas de Inspección y Búsqueda:
- **Búsqueda de Texto/Código:** Usa siempre `rg` (`-S` smart-case, `-n` números de línea).
  - *Límites estrictos:* Usa `--max-columns 300` y limita resultados con `--max-count 50`. NO uses tuberías destructivas como `| head -n 50` que disparan errores `SIGPIPE` rotos.
  - *Exclusiones:* Excluye lockfiles de forma predeterminada: `-g '!*.lock' -g '!package-lock.json'`.
- **Búsqueda de Archivos/Directorios:** Usa exclusivamente `fd` (`fd -t f`, `fd -t d`). NUNCA uses `find`. En búsquedas amplias limita la profundidad con `-d <N>`.
- **Manipulación de JSON:** Usa `jq` para extraer propiedades específicas; NUNCA vuelques payloads JSON completos al contexto.
- **Inspección de Git:** Usa formatos compactos (`git status -s`, `git diff --stat`, `git log --oneline -n 5`).

### Convenciones Git y Seguridad:
- **Mensajes:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, etc.) en una sola línea, en **inglés**, sin cuerpo extendido, y estrictamente SIN firmas de co-autoría ni menciones de asistentes de IA (prohibido `Co-authored-by:`).
- **Commits Atómicos:** Agrupa cambios relacionados en commits balanceados y lógicos.
- **Push Policy:** NUNCA ejecutes `git push` a menos que el usuario lo ordene explícitamente con comandos directos ("push", "pushea", "haz push").
- **Exclusiones y Caches:** Respeta `.gitignore`. En búsquedas desde `$HOME` (`~`), excluye estrictamente directorios pesados: `-E ".bun" -E ".cache" -E ".npm" -E ".cargo" -E ".local/share" -E ".venv" -E "venv"`.
- **Seguridad de Secretos:** NUNCA inspecciones ni expongas archivos `.env` reales que contengan credenciales en texto plano (inspecciona únicamente `.env.example`).
