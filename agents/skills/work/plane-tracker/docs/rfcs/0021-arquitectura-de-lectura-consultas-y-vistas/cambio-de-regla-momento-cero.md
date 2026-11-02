# Cambio de la regla externa "Momento Cero"

Parte de [0021](./README.md). La regla que indica a los agentes cuándo comprobar si un ticket ya existe cita el comando que este RFC retira. Este documento deja **mapeado** el cambio; no se ejecuta hasta la fase 2 ([`plan-de-migracion.md`](./plan-de-migracion.md)).

**Autorización:** el dueño de la herramienta pidió el 2026-11-02 cambiar la regla y dejarlo mapeado. La ejecución (editar la fuente y regenerar) ocurre en la fase 2, en la misma entrega que retira `search`.

## Dónde vive la regla

| Ubicación | Rol | Cómo se cambia |
| :--- | :--- | :--- |
| `agents/rules/src/work.md`, sección "Detección y Momento Cero" | **fuente única** de la regla del perfil de trabajo | se edita a mano |
| `agents/rules/dist/active-rules.md` | artefacto generado (solo lectura) | `make work` desde la raíz del repositorio de dotfiles |
| `~/.claude/CLAUDE.md`, `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md` | enlaces simbólicos al artefacto: la regla llega a los tres asistentes | se actualizan solos al regenerar |
| `SKILL.md` y `references/` de la skill | citas operativas de `plane-tracker search` (unas 15 referencias) | se editan a mano en la fase 2 |

No se edita `dist/` ni el archivo global a mano: se perdería en la siguiente regeneración.

## Texto vigente y texto objetivo

**Vigente** (bullet "Búsqueda Instantánea", con la clave de proyecto de ejemplo):

> El agente debe ejecutar `plane-tracker search "<intención>"` para comprobar en < 2ms si ya existe un ticket abierto en Plane o si se debe proponer uno nuevo.

**Objetivo:**

> El agente debe ejecutar `plane-tracker list --text "<intención>" --all-projects --json` para comprobar si ya existe un ticket (también cerrado o cancelado) en cualquier proyecto, o si se debe proponer uno nuevo. Con `total: 0` en la respuesta no hay coincidencias; con coincidencias, leer `state` y `state_group` antes de decidir. La búsqueda cubre título y etiquetas (`coverage.detail.text_fields`), no la descripción.

Cambios de fondo respecto al texto vigente:
1. **El comando**: `list --text`, con `--all-projects` porque un duplicado puede estar en otro proyecto.
2. **"Abierto" sale del texto**: el estado por defecto es `all` para ver cerrados y cancelados (un ticket cancelado también evita duplicar trabajo).
3. **Se declara la cobertura de la búsqueda** y se pide leerla (P5).
4. **Se retira la promesa de "< 2ms"**: es una medición que no se verifica en cada ejecución (P5); la búsqueda local sigue siendo rápida, pero la regla no lo afirma.

El bullet siguiente ("Acción Rápida": confirmar con el usuario y crear la rama del ticket, o proponer uno nuevo) **no cambia**: el consejo de rama que hoy imprime `search` pasa a vivir solo en esa regla y en `SKILL.md`.

## Orden de ejecución (en la fase 2)

1. Implementar `list --text` y sus pruebas (suite verde).
2. En la **misma entrega** que borra `search`: editar `agents/rules/src/work.md`, ejecutar `make work` y comprobar que `~/.claude/CLAUDE.md` (enlace) muestra el texto nuevo.
3. Actualizar `SKILL.md`, `references/GUIA_OPERATIVA_CLI_PLANE_TRACKER.md`, `references/ARQUITECTURA_SISTEMA_TRACKING_Y_TELEMETRIA.md`, `references/PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md`, `references/README.md` y `ARCHITECTURE.md`.
4. Verificar: `grep -rn "plane-tracker search"` vacío salvo la pista de `renamed.py`.

**Por qué ni antes ni después:** antes de que exista `list --text`, la regla mandaría a los agentes a un flag inexistente; después de retirar `search`, los agentes con la regla vieja recibirían código 2 con la pista de corrección (degradación aceptable, no deseable). Los agentes **ya cargados** llevan la regla vieja en su contexto: la pista de `renamed.py` (`search` → `list --text`) es la red de seguridad hasta que reinicien la sesión.

## Qué comprobar tras el cambio

- La regla llega a los tres asistentes (los enlaces apuntan a `dist/active-rules.md` regenerado).
- Una sesión nueva ejecuta `plane-tracker list --text ... --all-projects --json` al recibir una intención de trabajo.
- Ninguna otra regla o skill del repositorio de dotfiles cita `plane-tracker search` (se comprobó con `rg` en `agents/` al redactar este documento; los worktrees no cuentan).
