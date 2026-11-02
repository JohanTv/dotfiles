# Cambio de la regla externa "Momento Cero"

Parte de [0021](./README.md) (versión 2). La regla que indica a los agentes cuándo comprobar si un ticket ya existe cita el comando que este RFC retira. Este documento deja **mapeado** el cambio; no se ejecuta hasta la fase 2 ([`plan-de-migracion.md`](./plan-de-migracion.md)).

**Autorización:** el dueño pidió el 2026-11-02 cambiar la regla y dejarlo mapeado. La ejecución (editar la fuente y regenerar) ocurre en la fase 2, en la misma entrega que retira `search`. La **redacción del texto objetivo fue confirmada por el dueño el 2026-11-02**; solo falta ejecutarla en la fase 2.

## Dónde vive la regla

| Ubicación | Rol | Cómo se cambia |
| :--- | :--- | :--- |
| `agents/rules/src/work.md`, sección "Detección y Momento Cero" | **fuente única** de la regla del perfil de trabajo | se edita a mano |
| `agents/rules/dist/active-rules.md` | artefacto generado, ignorado por Git | `make work` desde la raíz del repositorio de dotfiles |
| `~/.claude/CLAUDE.md`, `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md` | enlaces simbólicos al artefacto: la regla llega a los tres asistentes | se actualizan al regenerar |
| `SKILL.md` y `references/` de la skill | citas operativas de `plane-tracker search` | se editan a mano en la fase 2 |

No se edita `dist/` ni el archivo global a mano: se perdería en la siguiente regeneración. El artefacto se regenera **en cada máquina donde se use el perfil** (el repositorio se usa en más de una: WSL y Ubuntu); `make doctor` comprueba los enlaces.

## Texto vigente y texto objetivo

**Vigente** (bullet "Búsqueda Instantánea", con la clave de proyecto de ejemplo):

> El agente debe ejecutar `plane-tracker search "<intención>"` para comprobar en < 2ms si ya existe un ticket abierto en Plane o si se debe proponer uno nuevo.

**Objetivo (confirmado):**

> El agente debe ejecutar `plane-tracker list --text "<intención>" --all-projects --limit 5 --brief --json` para comprobar si ya existe un ticket (también cerrado o cancelado) en cualquier proyecto. Antes de concluir que no hay duplicado debe leer `coverage`: si `unavailable` no está vacío, `stale` es `true` o `complete` no es `true`, el resultado **no prueba ausencia** y debe decirlo. Con coincidencias, leer `state` y `state_group` antes de decidir. La búsqueda cubre título y etiquetas (`coverage.detail.text_fields`), no la descripción.

Cambios de fondo respecto al texto vigente:
1. **El comando**: `list --text`, con `--all-projects` (un duplicado puede estar en otro proyecto) y `--limit 5` (el coste en tokens de una respuesta con filas completas es mayor que el de `search`; el límite lo acota. Medido: ver abajo).
2. **"Abierto" sale del texto**: el estado por defecto es `all` para ver cerrados y cancelados.
3. **Se exige leer la cobertura** (P5): hoy la regla diría "total 0 = no hay duplicado" aunque un proyecto no respondiera.
4. **Se retira la promesa de "< 2 ms"**: es una medición que no se verifica en cada ejecución.
5. **Pendiente de evaluar:** si una vista breve del resultado (solo `ticket`, `title`, `state`, `state_group`, `project`) para este uso reduce tokens sin perder decisión; y si la guarda de duplicados debería vivir en `create` (`create --check`) y no en la regla (ver [`alternativas.md`](./alternativas.md)).

El bullet siguiente ("Acción Rápida": confirmar con el usuario y crear la rama del ticket, o proponer uno nuevo) **no cambia**: el consejo de rama que hoy imprime `search` pasa a vivir solo en esa regla y en `SKILL.md`.

## Referencias reales a retirar (verificadas con `rg`)

`plane-tracker search` aparece en **14 líneas de 6 archivos** del árbol de dotfiles (sin contar `.worktrees`): `rules/src/work.md` (1), `SKILL.md` (2) y, en `references/`, `GUIA_OPERATIVA_CLI_PLANE_TRACKER.md` (7), `ARQUITECTURA_SISTEMA_TRACKING_Y_TELEMETRIA.md` (2), `PROTOCOLO_RELEVO_ASINCRONO_HANDOFF.md` (1) y `README.md` (1). Además hay **menciones sin el prefijo** que también deben revisarse: `ARCHITECTURE.md` (regla 1 y mapa de módulos), `scripts/plane_cli/__init__.py`, `cmd_read.py` (docstring), `GUIA_OPERATIVA` (tabla de nomenclatura) y `ARQUITECTURA_SISTEMA` (líneas de lectura).

## Lo que la validación real cambió

- **El comando objetivo falla hoy** en un workspace con proyectos sin acceso (403 aborta `list --all-projects`); la regla **solo puede cambiarse después de la fase 1**, que lo corrige ([`hechos-de-la-api.md`](./hechos-de-la-api.md)).
- **Tokens medidos** (consulta real, 5 resultados): `search --json` actual 314; sobre completo compacto 726; sobre con filas breves 336. Por eso la regla pide `--limit 5` y se propone la **vista breve** (decisión 11 del README).
- Existe un endpoint de Plane que busca por texto en todo el workspace en 1 GET (máximo 10 resultados, sin estado): sirve como primer filtro barato de una guarda en `create`, no como sustituto de `list --text`.

## Orden de ejecución (en la fase 2)

1. Implementar `list --text` y sus pruebas (fase 1, suite verde).
2. En la **misma entrega** que borra `search`: editar `agents/rules/src/work.md`, ejecutar `make work` y comprobar que `~/.claude/CLAUDE.md` (enlace) muestra el texto nuevo. Repetirlo en cada máquina.
3. Actualizar `SKILL.md`, las referencias y `ARCHITECTURE.md` (incluidas las menciones sin prefijo).
4. Verificar con el criterio de abajo.

**Por qué ni antes ni después:** antes de que exista `list --text`, la regla mandaría a un flag inexistente; después de retirar `search`, los agentes con la regla vieja recibirían código 2 con la pista traducida (degradación aceptable, no deseable). Los agentes **ya cargados** llevan la regla vieja en su contexto: la pista de `renamed.py` es la red de seguridad hasta que reinicien la sesión.

## Criterio de verificación

```bash
rg -F "plane-tracker search" agents --glob '!**/.worktrees/**' --glob '!**/docs/rfcs/0021-*/**' --glob '!**/dist/**'
```
debe devolver **solo** la pista de `renamed.py` y las pruebas de esa pista. Los documentos de este RFC y el artefacto regenerado quedan excluidos porque **citan el comando retirado a propósito**. Además:

- La regla nueva llega a los tres asistentes (los enlaces apuntan a `dist/active-rules.md` regenerado, en cada máquina).
- Una **sesión limpia** recibe una intención de trabajo y ejecuta `plane-tracker list --text ... --all-projects --limit 5 --brief --json` y lee `coverage`.
- `test_every_route_is_cited` sigue verde (cada ruta de comando se cita en `SKILL.md`).
