# Directrices de Exploración y Operaciones CLI

### Herramientas Primarias:
- **Búsqueda de código y texto:** Usa siempre `rg` (sensible con `-S`, números con `-n`, literales con `-F`).
  - *Ahorro de tokens:* Usa `-l` para listar solo archivos coincidentes antes de volcar contenido.
  - *Límites estrictos:* Usa `--max-columns 300` y `| head -n 50` para evitar saturar el contexto. Excluye lockfiles con `-g '!*.lock' -g '!package-lock.json'`.
- **Búsqueda de archivos y carpetas:** Usa `fd` (no `find`). Limita profundidad con `-d <N>` en exploraciones amplias (ej. `fd -t d <nombre>`, `fd -t f <nombre>`).
- **Consultas JSON:** Usa `jq` para extraer campos concretos en lugar de volcar archivos enteros (ej. `jq '.dependencies' package.json`; para claves con `$` o caracteres especiales, usa comillas: `jq '."$defs"'`).
- **Reemplazos de texto (`sd`):** Usa `sd` para sustituir texto directamente en archivos (ideal para archivos grandes o cambios masivos sin cargar todo a contexto): `sd 'buscar_regex' 'reemplazo' archivo`.
- **Inspección Git:** Usa formatos compactos (`git status -s`, `git diff --stat`, `git log --oneline -n 5`).

### Convenciones y Commits de Git:
- **Mensajes:** Estándar (Conventional Commits: `feat:`, `fix:`, `refactor:`, `chore:`, etc.), siempre en **inglés**, solo el título en una línea (sin descripción/cuerpo extenso, y **sin co-autor** ni firmas de IA tipo `Co-authored-by`).
- **Agrupación:** Si hay múltiples cambios, agrúpalos en commits lógicos y atómicos con criterio equilibrado (evita tanto un único commit masivo como una fragmentación excesiva).
- **Control de Push:** NUNCA ejecutes `git push` a menos que el usuario lo solicite de manera explícita en su mensaje (ej. "haz push", "pushea", "sube los cambios").

### Exclusiones por defecto y Seguridad:
- **Dependencias y cachés:** Respeta siempre `.gitignore`. En búsquedas desde `$HOME` (`~`), excluye estrictamente cachés masivas: `-E ".bun" -E ".cache" -E ".npm" -E ".cargo" -E ".local/share" -E ".venv" -E "venv"`. Prioriza siempre el espacio de trabajo activo.
- **Secretos (.env):** Nunca busques ni expongas archivos `.env*` con credenciales reales en salidas abiertas (permite únicamente `.env.example`).

