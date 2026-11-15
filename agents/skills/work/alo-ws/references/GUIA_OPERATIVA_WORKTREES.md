# Guía Operativa de Orquestación Multi-Repo (`plane-worktree`)

Esta guía complementa el `SKILL.md` de `plane-worktree` con el detalle procedural, casos de uso avanzados, resolución de conflictos y gestión de respaldos.

---

## 1. Ciclo de Vida de un Espacio de Trabajo Multi-Repo

Cuando una iniciativa técnica (ej. `OMNIFY-238`) abarca más de un repositorio (ej. backend y detonador), no deben crearse ramas locales sueltas de forma manual. Se utiliza `plane-worktree` para generar un contenedor unificado en `.worktrees/`.

### Creación (`add`):
```bash
# Ejemplo: ticket OMNIFY-238 con backend y detonador
plane-worktree add OMNIFY-238 operator-recovery omnify-backend omnify-detonador-sms --type feat --base dev
```

#### Fases de Ejecución:
1. **Fase 1 (Pre-flight Transaccional):**
   - Valida que `.worktrees/` exista en la raíz del workspace.
   - Detecta si los nombres de repositorios son únicos.
   - Resuelve las rutas absolutas de cada repositorio.
   - Verifica que `origin/<base>` exista en los remotos.
   - Verifica que la rama destino no esté actualmente checkouteada en otro worktree.
   - Si una rama local preexistente diverge de `origin/<base>`, aborta inmediatamente para evitar código zombie (salvo que se pase `--reuse-branch`).
   - Si cualquiera de estas comprobaciones falla, la operación se detiene **sin tocar el sistema de archivos**.
2. **Fase 2 (Mutaciones Atómicas):**
   - Crea el directorio contenedor `.worktrees/<TICKET>-<SLUG>/`.
   - Ejecuta `git worktree add` para cada repositorio vinculando la rama correspondiente.
   - Imprime el resumen de ramas y la ruta directa para navegar con `cd`.

### Reutilización de Ramas (`--reuse-branch`):
Si necesitas retomar un trabajo previo donde la rama local ya contiene avances propios que aún no están en `origin/<base>`:
```bash
plane-worktree add OMNIFY-238 operator-recovery omnify-backend --reuse-branch
```

---

## 2. Inspección de Árboles (`list` / `ls`)

Permite obtener una vista consolidada de todos los contenedores y el estado de sus repositorios:

```bash
# Vista formateada en terminal
plane-worktree list

# Salida estructurada JSON para consumo de scripts/agentes
plane-worktree list --json
```

Cada repositorio reporta:
- Rama actual y último commit (`hash 'mensaje'`).
- Estado de los archivos: `(clean)` o `(dirty: N archivos)`.

---

## 3. Auditoría de Salud y Podabilidad (`audit`)

Analiza la integrabilidad de cada worktree cruzando tres fuentes de verdad:
1. **Filesystem:** Detecta si hay archivos modificados o sin commitear (`clean` vs `dirty`).
2. **Git Local:** Determina si la rama fue integrada en la base mediante:
   - Ancestro directo (`git merge-base --is-ancestor`).
   - Detección trifásica en memoria de Squash/Rebase Merges (`git merge-tree --write-tree origin/<base> HEAD`).
3. **Plane Cache (SQLite):** Consulta `~/.cache/plane/worklogs.db` (`issues_cache`) para verificar si el ticket asociado está `Completado`, `Cancelado` o en progreso.

```bash
# Auditar todos los contenedores (sincroniza origin automáticamente)
plane-worktree audit

# Auditar un contenedor o ticket específico
plane-worktree audit OMNIFY-238

# Auditoría rápida offline sin conexión de red
plane-worktree audit --no-fetch
```

### Clasificación de Estados:
- `✔ [SEGURO PARA PODAR]`: 100% integrado a la base y sin archivos pendientes.
- `✖ [MERGEADOS CON CAMBIOS]`: Integrado en Git pero con modificaciones locales sin commitear.
- `○ [EN CURSO / ACTIVOS]`: Ramas con trabajo activo en desarrollo.
- `⚠ [ABANDONADOS CON CAMBIOS]`: Ticket cancelado en Plane con archivos locales sin commitear. Requiere `--include-stale` para poda con respaldo.
- `⚠ [ABANDONADOS LIMPIOS]`: Ticket cancelado en Plane y repositorios limpios.
- `◐ [PARCIALMENTE MERGEADO]`: Algunos repositorios mergeados y otros pendientes.
- `✖ [BLOQUEADOS POR CAMBIOS]`: Rama no integrada y con cambios locales sin commitear.
- `🛡 [RAMA PRINCIPAL PROTEGIDA]`: Rama `main`, `master`, `dev` o `staging` (inmune a poda).

---

## 4. Poda Asistida y Respaldos Comprimidos (`prune`)

### Modo Dry-Run (Por defecto):
Muestra exactamente qué contenedores y ramas se eliminarían sin alterar nada en disco:
```bash
plane-worktree prune
```

### Poda Segura de Contenedores 100% Integrados:
Elimina únicamente worktrees y ramas que hayan sido integrados y estén completamente limpios:
```bash
plane-worktree prune --execute
```
Acciones realizadas:
1. Ejecuta `git worktree remove` en cada repositorio.
2. Elimina la rama local (`git branch -d` para merge directo, o `-D` seguro para squash-merge verificado).
3. Ejecuta `git worktree prune` para limpiar referencias administrativas de Git.
4. Elimina la carpeta contenedora vacía en `.worktrees/`.

### Poda de Tickets Cancelados/Abandonados con Respaldo Automático (`--include-stale`):
Si un ticket fue cancelado en Plane o quedó abandonado con archivos sin commitear, `plane-worktree` exige la bandera explícita `--include-stale`.
Antes de eliminar el contenedor, empaqueta automáticamente todo su contenido en un archivo comprimido `.tar.gz`:

```bash
plane-worktree prune OMNIFY-123-cancelled --execute --include-stale
```

- **Ubicación del respaldo:** `~/.cache/plane/worktree-backups/<contenedor>-<timestamp>.tar.gz`
- **Verificación:** Valida que el archivo comprimido exista y tenga tamaño mayor a cero antes de proceder a la eliminación.
- **Directorio personalizado:** Puedes especificar `--backup-dir /ruta/alternativa`.

### Recuperación Forense de un Respaldo:
Para restaurar archivos de un contenedor podado previamente:
```bash
tar -ztvf ~/.cache/plane/worktree-backups/OMNIFY-123-cancelled-20261102-174500.tar.gz
tar -zxvf ~/.cache/plane/worktree-backups/OMNIFY-123-cancelled-20261102-174500.tar.gz -C /tmp/recuperacion/
```
