---
name: dotfiles-sync
description: Diagnostica, audita y sincroniza configuraciones locales del host (Alacritty, Zellij, Zsh, reglas de IA, etc.) con el repositorio dotfiles. Activa esta habilidad cuando el usuario pregunte si hay cambios locales, si sus configuraciones están sincronizadas con GitHub, o pida auditar/actualizar el repositorio dotfiles.
---

# Skill: Diagnóstico y Sincronización de Dotfiles (`dotfiles-sync`)

Esta habilidad permite a los agentes de IA auditar la integridad de las configuraciones del sistema, verificar si archivos en `$HOME` fueron modificados fuera de Git o si se rompieron enlaces simbólicos, y mantener el repositorio `dotfiles` actualizado.

---

## 1. Herramienta Principal: `dotfiles-doctor`

El script global [`dotfiles-doctor`](file:///home/johantv/.local/bin/dotfiles-doctor) (código fuente en [~/Code/dotfiles/bin/common/dotfiles-doctor](file:///home/johantv/Code/dotfiles/bin/common/dotfiles-doctor)) realiza una auditoría completa del entorno.

### Modos de Ejecución:

```bash
# Diagnóstico visual rápido:
dotfiles-doctor

# Salida estructurada JSON (ideal para procesar en agentes):
dotfiles-doctor --json

# Restaurar symlinks desconectados o rotos:
dotfiles-doctor --fix
```

---

## 2. Flujo de Trabajo del Agente

Cuando el usuario pida:
* *"¿Hay cambios locales en Alacritty o Zellij?"*
* *"Valida si mis configuraciones están sincronizadas con el repo"*
* *"Revisa si toqué algún archivo en mi máquina y actualiza dotfiles"*

El agente debe:

1. **Ejecutar el diagnóstico:**
   ```bash
   dotfiles-doctor --json
   ```
2. **Interpretar los resultados:**
   * **`targets` con `status != "OK"`:** Indica que un archivo en `$HOME` no es un enlace simbólico o fue desconectado.
   * **`git.changed_files`:** Muestra archivos modificados o nuevos dentro del repositorio `dotfiles` (la ruta exacta viene en `.dotfiles_dir`).
3. **Inspeccionar diferencias (`git diff`):**
   Si hay cambios en el repositorio, inspeccionar con `git -C <dotfiles_dir> diff --stat` para revisar qué configuraciones cambiaron.
4. **Validar sintaxis según la herramienta afectada:**
   * Si cambió **Zellij**: Ejecutar `zellij setup --check` para garantizar cero errores de KDL.
   * Si cambió **Zsh**: Probar carga limpia con `zsh -n ~/.zshrc`.
   * Si cambió **OpenCode**: Validar con `opencode debug config`.
5. **Guardar cambios en Git:**
   * Crear commits atómicos siguiendo Conventional Commits en inglés sin co-autor.
   * **REGLA CRÍTICA:** NUNCA ejecutar `git push` a menos que el usuario lo solicite de manera textual en su mensaje.
