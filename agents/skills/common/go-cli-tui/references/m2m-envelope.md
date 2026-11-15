# Protocolo M2M Canónico: ResponseEnvelope y Auto-Reparación para Agentes de IA

Este documento define el estándar de interfaz máquina a máquina (M2M) para herramientas de línea de comandos en Go cuando son consumidas por agentes autónomos de IA (Claude Code, Gemini CLI, OpenCode) o pipelines de CI/CD.

---

## 1. Reglas Inquebrantables de la Salida Estructurada

1. **Canal Exclusivo `stdout`:** En modo `--json`, `stdout` es el **único** canal para emitir datos o errores.
2. **Silencio Absoluto en `stderr` (0 bytes):** Ante cualquier error de validación, sintaxis o lógica de negocio en modo `--json`, `stderr` debe permanecer en 0 bytes. La contaminación de `stderr` con advertencias o trazas rompe capturas Unix (`OUTPUT=$(app --json)` o tuberías hacia `jq`).
3. **Sincronía de Códigos POSIX:** Prohibido emitir código de salida `0` cuando `"ok": false`. El código de salida del proceso debe ser diferente de cero (`!= 0`).
4. **Campos de Auto-Reparación (Self-Healing Loop):** El error debe proporcionar la información necesaria para que un LLM se auto-corrija sin consultar documentación externa.

---

## 2. Esquema JSON Canónico (`ResponseEnvelope`)

```json
{
  "ok": false,
  "error": {
    "code": "TARGET_WORKSPACE_NOT_FOUND",
    "category": "user_input",
    "message": "No existe un worktree activo para el ticket OMNIFY-175",
    "target": "OMNIFY-175",
    "hint": "Crea primero el entorno de trabajo usando 'alo ws create OMNIFY-175'",
    "suggested_command": "alo ws create OMNIFY-175",
    "recoverable": true,
    "context": {
      "active_worktrees": 3,
      "base_path": ".worktrees/"
    }
  },
  "data": null
}
```

### Definición de Campos:
- `ok` (bool): `true` en operaciones exitosas, `false` ante cualquier error.
- `error.code` (string): Identificador único inmutable en `SCREAMING_SNAKE_CASE`. Los agentes lo usan para ramificar su lógica de reintento.
- `error.category` (string): Categoría semántica (`user_input`, `state_conflict`, `auth`, `upstream_service`, `internal`).
- `error.message` (string): Explicación técnica concisa y legible.
- `error.target` (string, opcional): El parámetro, bandera, archivo o identificador culpable del fallo.
- `error.hint` (string, opcional): Instrucción directa en lenguaje natural para subsanar el error.
- `error.suggested_command` (string, opcional): Comando exacto que el agente puede invocar de inmediato para resolver el estado.
- `error.recoverable` (bool): Indica si la operación puede tener éxito reintentando o corrigiendo argumentos (`true`), o si es un fallo fatal no recuperable (`false`).
- `error.context` (object, opcional): Metadatos adicionales para depuración.

---

## 3. Matriz de Códigos de Salida POSIX Semánticos

| Código | Constante Go | Categoría | Significado Semántico |
| :---: | :--- | :--- | :--- |
| `0` | `ExitSuccess` | - | Operación completada con éxito (`ok: true`). |
| `1` | `ExitGeneralError` | `internal` | Fallo de ejecución no clasificado o genérico. |
| `2` | `ExitUsageError` | `user_input` | Argumentos faltantes, banderas inválidas o sintaxis incorrecta. |
| `3` | `ExitAuthError` | `auth` | Fallo de credenciales, token ausente, expirado o permisos denegados. |
| `4` | `ExitNotFound` | `user_input` | Recurso, archivo, ticket o entidad objetivo no encontrada. |
| `5` | `ExitTransientError`| `upstream_service` | Error temporal de red, timeout o upstream reintentable con backoff. |
| `70` | `ExitSoftwareError` | `internal` | Pánico en tiempo de ejecución capturado por `SafeExecute`. |

---

## 4. Implementación de Resiliencia con `SafeExecute`

Envuelve el punto de entrada de la aplicación para interceptar `panic` imprevistos y emitir un envelope estructurado en lugar de un stack trace roto:

```go
func SafeExecute(jsonMode bool, fn func() error) {
    defer func() {
        if r := recover(); r != nil {
            EmitError(
                fmt.Errorf("%v", r),
                ErrorDetail{
                    Code:        "INTERNAL_PANIC",
                    Category:    CategoryInternal,
                    Message:     fmt.Sprintf("Panic recuperado: %v", r),
                    Hint:        "Error interno de runtime. Ejecuta con banderas verbose para trazas de depuración.",
                    Recoverable: false,
                },
                ExitSoftwareError,
                jsonMode,
            )
        }
    }()

    if err := fn(); err != nil {
        // Manejo controlado de errores devueltos
    }
}
```
