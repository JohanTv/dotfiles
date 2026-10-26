---
name: find-session
description: Busca de forma instantánea IDs de sesiones y conversaciones pasadas en Gemini (agy), Claude Code y OpenCode a partir de temas o palabras clave. Activa esta habilidad cuando el usuario pregunte por sesiones anteriores, cómo reanudar un chat previo o busque información tratada en conversaciones pasadas.
---

# Skill: Búsqueda Rápida de Sesiones (Gemini, Claude Code y OpenCode)

Esta habilidad permite a los agentes (Gemini CLI / `agy`, Claude Code y OpenCode) localizar de inmediato identificadores (`UUID` / IDs) de conversaciones y sesiones pasadas sin necesidad de realizar escaneos manuales o comandos lentos.

> [!IMPORTANT]
> Si el usuario indica o solicita buscar **exclusivamente en un agente**, usa siempre su flag correspondiente para acotar de inmediato el espacio de búsqueda:
> * `-g` para Gemini (`agy`)
> * `-c` para Claude Code
> * `-o` para OpenCode

## 1. Herramienta Principal: `find-session`

El script global [find-session](file:///home/johantv/.local/bin/find-session) (código fuente en `bin/common/find-session` dentro del repositorio dotfiles) inspecciona directamente las bases de datos y registros locales de los tres asistentes.

### Sintaxis de Uso

```bash
# Búsqueda general en todos los agentes por palabra clave o tema:
find-session <palabra_clave>

# Búsqueda filtrada por agente específico:
find-session -g <palabra_clave>    # Solo Gemini (agy)
find-session -c <palabra_clave>    # Solo Claude Code
find-session -o <palabra_clave>    # Solo OpenCode

# Listar las últimas N sesiones recientes:
find-session --recent -n 5

# Búsqueda profunda dentro del contenido de transcripciones/mensajes completos:
find-session -d "<término complejo>"

# Salida estructurada JSON (ideal para procesar en agentes):
find-session --json <palabra_clave>
```

---

## 2. Cómo Reanudar Sesiones

Una vez obtenido el `ID` de la sesión:

### En Gemini (`agy`):
* **Desde la terminal:**
  ```bash
  agy --conversation <session-id>
  ```
* **Dentro del TUI interactivo de agy:**
  ```text
  /resume <session-id>
  ```

### En Claude Code:
* **Desde la terminal:**
  ```bash
  claude --resume <session-id>
  ```

### En OpenCode:
* **Desde la terminal:**
  ```bash
  opencode -s <session-id>
  ```

---

## 3. Comportamiento Esperado del Agente

Cuando el usuario pregunte algo como:
* *"¿Qué hablamos en la sesión donde configuramos Alacritty?"*
* *"Busca la sesión donde implementamos helloworld en python"*
* *"Dame el ID de la conversación anterior de ayer"*

El agente debe:
1. Ejecutar de inmediato `find-session <tema>` (o con `-j` para salida procesable).
2. Si encuentra la sesión, mostrar al usuario:
   * **Agente emisor:** (`[agy]`, `[claude]`, `[opencode]`)
   * **ID exacto de la sesión**
   * **Fecha y hora**
   * **Comando para reanudarla**
   * Un breve resumen del contexto o el snippet de coincidencia.
3. Si el usuario pide retomar esa sesión, indicar el comando exacto correspondiente al agente.
