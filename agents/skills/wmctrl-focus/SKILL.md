---
name: wmctrl-focus
description: >-
  Procedimiento para crear atajos de teclado en Ubuntu GNOME (X11) que enfoquen
  una ventana existente usando wmctrl o abran la aplicación si no está corriendo.
---

# Procedimiento: Atajos de Enfoque de Ventana con wmctrl

## 1. Entorno del Sistema
- **SO**: Ubuntu con GNOME Shell en sesión **X11**.
- **Herramienta de ventana**: `wmctrl` (ubicado en `~/.local/bin/wmctrl`).
- **Ubicación scripts**: `~/Code/toolbox/scripts/` (enlazados a `~/.local/bin/`).

## 2. Pasos para agregar un nuevo atajo

### Paso A: Obtener la clase de ventana (`WM_CLASS`)
1. Abrir la aplicación objetivo.
2. Ejecutar en terminal:
   ```bash
   wmctrl -lx | grep -i <nombre_aplicacion>
   ```
   *La segunda columna indica el identificador de ventana, y la tercera columna (ej. `org.gnome.Nautilus.org.gnome.Nautilus` o `Alacritty.Alacritty`) es la `WM_CLASS`.*

### Paso B: Crear el script en `scripts/`
Crear `~/Code/toolbox/scripts/focus-<app>` con permisos de ejecución (`chmod +x`):
```bash
#!/usr/bin/env bash
# Focus existing <App> window, or start a new one if not running
export PATH="$HOME/.local/bin:$PATH"

if ! wmctrl -x -a <WM_CLASS>; then
    <comando_lanzamiento> &
fi
```
Crear enlace simbólico en `~/.local/bin/`:
```bash
ln -sf ~/Code/toolbox/scripts/focus-<app> ~/.local/bin/focus-<app>
```

### Paso C: Asignar atajo en GNOME
Registrar el atajo personalizado usando `gsettings`:
```bash
KEY_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-<app>/"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEY_PATH name "<App>"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEY_PATH command "/home/johantv/.local/bin/focus-<app>"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEY_PATH binding "<Super><tecla>"
```
Y agregar el `$KEY_PATH` a la lista de `custom-keybindings` asegurando no duplicar.
