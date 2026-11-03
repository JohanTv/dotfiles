---
id: "0002"
title: Gestión de worktrees multi-repo por ticket
status: implementado
created: 2026-10-31
summary: Script independiente que crea, por ticket, un worktree en cada repo implicado con rama y base verificadas.
---

# 0002 · Gestión de worktrees multi-repo por ticket

- **Área:** superficie nueva `worktree add`; si se implementa como script, `bin/work/plane-worktree`.

## Contexto

Al iniciar un requerimiento que cruza varios repositorios (por ejemplo un servicio de envío + un backend) hay que, por cada repo: crear una carpeta contenedora por ticket, elegir la rama base remota, hacer `fetch`, inventar el nombre de la rama, crear el worktree y comprobar que no colisiona. Son 4-6 comandos por repo, con dos decisiones semánticas en medio y varios modos de fallo silenciosos.

Layout deseado:

```text
.worktrees/PROJ-238-operator-recovery/
├── repo-envio/             feat/PROJ-238-envio-reintento
└── repo-backend/           feat/PROJ-238-webhook-operador
```

## Evidencia verificada

| Hecho | Ubicación | Consecuencia |
| :--- | :--- | :--- |
| Existe un generador de nombre de rama por fase, dentro de `create` | `scripts/plane_cli/cmd_tickets_write.py:220-241` | Un comando nuevo duplicaría esa lógica si no se extrae antes. |
| Ese generador mapea `[RFC]` → `spike` | `cmd_tickets_write.py:226-236` | Para un ticket `[RFC]` trabajado como `feat/`, produce la rama equivocada. |
| Deriva el slug del título con `re.sub(r"[^a-zA-Z0-9]+", "-", ...)`, truncado a 35 | `cmd_tickets_write.py:238-240` | Pierde tildes y corta palabras: `dise-o-del-reintento-y-rastro-cuand`. |
| Hay un tercer sitio con un `feat/` hardcodeado | `cmd_read.py:300` | Unificar nombres toca también `search`, no solo `create`. |
| El árbol de comandos raíz es explícito y cerrado | `scripts/plane_cli/cli.py:24-47` | Un verbo raíz nuevo rompe la convención; un grupo es lo previsto. |
| La ayuda global tiene un tope de 280 columnas (1120 caracteres) | `tests/test_cli_tree.py:101` | Hoy se usan 1080: quedan 40 caracteres. Un grupo con tres verbos lo revienta. |
| `main()` valida `PLANE_BASE_URL` y `PLANE_API_KEY` antes de despachar | `cli.py:111-112`, contrato en `ARCHITECTURE.md:199` | Un comando que solo ejecuta git heredaría una dependencia de Plane que no necesita. |
| `origin/dev` no existe en todos los repos (hay repos con `main` + `staging`, y repos con solo `main`) | `git branch -r` | `dev` no puede ser un default ciego. |
| Pueden existir dos clones del mismo repo en ramas distintas | `Code/repo/`, `Code/repo-otro-clon/` | Un mapa `nombre → ruta` en configuración es ambiguo y envejece mal. |
| `git -C repo worktree add ruta-relativa` resuelve contra el repo, no contra el cwd | comportamiento de git | Hay que pasar rutas absolutas siempre. |

## Propuesta original y descartes

| Pieza | Veredicto | Motivo |
| :--- | :--- | :--- |
| Fan-out a N repos | Se mantiene | Es el único valor nuevo real. |
| `--type` derivado del título | Descartada | `[RFC]` → `spike` contradice la decisión de trabajar un ticket `[RFC]` como `feat`. |
| `--description` derivada del título | Descartada | Genera slugs mutilados. |
| `PLANE_REPOS` (nombre → ruta) | Descartada | Segunda fuente de verdad, ya ambigua. |
| `origin/dev` por defecto sin verificar | Descartada | Falla en repos que no tienen `dev`. |
| `remove` destructivo ciego | Descartada | Borrar carpetas sin auditar estado destruye cambios no guardados. |
| `list`, `audit` y `prune` asistido | Adoptadas | Visibilidad multi-repo agregada, detección de squash-merge con `git merge-tree`, consulta offline a Plane SQLite, modo dry-run por defecto y respaldo automático `.tar.gz` para ramas abandonadas/canceladas con cambios (`--include-stale`). |
| `README.md` generado en el padre | Descartada | Plantilla que se desincroniza; el ticket ya es la fuente. |
| `--reuse-branch` | Adoptada como salvaguarda | En lugar de un attach silencioso (que reviviría código zombie si la rama local diverge de origin/<base>), el pre-flight verifica si la rama local diverge; si diverge, exige `--reuse-branch` explícitamente para proceder. |
| Validación de carpeta base | Adoptada | Exige que `.worktrees` (o `--dir`) exista previamente antes de crear worktrees, evitando contaminar subcarpetas con repositorios anidados no deseados. |
| Flag companion `--branch-slug` | Adoptada en `create` | Permite especificar el slug en inglés al crear el ticket en Plane, desacoplándolo del título en español y limpiando acentos con Unicode NFKD. |
| `--no-fetch` | Se mantiene | Sin él no hay uso offline ni test determinista. |
| Extraer `branch.py` | Aplazada | Unificaría 3 sitios, pero obliga a regenerar goldens de `create` y `search`. |

## Ubicación: CLI o script

- **Grupo en el CLI** (`plane-tracker worktree add`): un solo punto de entrada, pero el comando no necesita ningún dato de Plane y hereda el gate de credenciales; solo cabe un verbo por el presupuesto de ayuda; y el alta exige 5 puntos de documentación con tests y goldens.
- **Script independiente** (`bin/work/plane-worktree`): no habla con Plane, no toca el árbol de comandos, no consume presupuesto de ayuda y se testea aislado.

**Decisión:** script independiente. La diferencia no es la lógica (es la misma), es la puerta de entrada y su precio.

## Contrato

```bash
# Alta y orquestación multi-repo
plane-worktree add TICKET DESCRIPTION REPO[=SLUG]... \
  [--type feat] [--base dev] [--dir .worktrees] [--reuse-branch] [--no-fetch]

# Inspección centralizada de worktrees y estado git
plane-worktree list [--dir .worktrees] [--json]

# Auditoría de salud y podabilidad (Filesystem + Git merge-tree + Plane SQLite)
plane-worktree audit [TARGET] [--dir .worktrees] [--no-fetch] [--json]

# Poda asistida segura (Dry-run por defecto, --include-stale con respaldo .tar.gz)
plane-worktree prune [TARGET] [--dir .worktrees] [--execute] [--include-stale] [--backup-dir DIR] [--no-fetch] [--json]
```

| Elemento | Regla |
| :--- | :--- |
| Carpeta padre | `<dir>/<TICKET>-<DESCRIPTION>`; `--dir` se resuelve contra el cwd y se imprime en absoluto. Exige que `<dir>` exista previamente. |
| Carpeta hija | `basename(git rev-parse --show-toplevel)` del repo. |
| Rama | `<type>/<TICKET>-<SLUG>`, con `SLUG` propio del repo o el `DESCRIPTION` compartido. |
| `--type` | Explícito, default `feat`. No se deriva del título. |
| `--base` | Default `dev`. Se verifica `refs/remotes/origin/<base>` antes de crear. |
| `--repo` | Ruta a un clon; un nombre suelto se resuelve contra el cwd y sus hermanos exigiendo una única coincidencia. |
| `--reuse-branch` | Permite hacer attach a una rama local existente que diverge de `origin/<base>`. Sin este flag, falla en pre-flight como salvaguarda. |
| Fetch | Best-effort implícito en `add`, `audit` y `prune` (deduplicado por repo base en paralelo; si falla, aviso y continúa con refs locales). `--no-fetch` disponible para ejecución offline instantánea. |

Matriz de comportamiento:

| Situación | Resultado |
| :--- | :--- |
| El destino ya es un worktree de ese repo en esa rama | Aviso "ya existe", exit 0 (idempotente). |
| La rama existe, coincide con `origin/<base>` y no está checkouteada | `git worktree add <dest> <rama>` (attach seguro). |
| La rama existe, diverge de `origin/<base>` y se pasó `--reuse-branch` | Aviso de reutilización y `git worktree add <dest> <rama>` (attach permitido). |
| La rama existe, diverge de `origin/<base>` y NO se pasó `--reuse-branch` | Error en Fase 1 abortando la operación (protección contra ramas zombies). |
| La rama está checkouteada en otro worktree | Error en Fase 1 indicando la ruta ocupada. |
| `origin/<base>` no existe | Error en Fase 1 listando las ramas remotas disponibles. |
| El directorio base (`.worktrees`) no existe | Error en Fase 1 advirtiendo que debe crearse en la raíz del workspace (con pista de ruta si se ejecutó en subcarpeta). |
| El destino existe, no está vacío y no es worktree | Error en Fase 1, sin tocar nada. |

## Riesgos

| Riesgo | Severidad | Mitigación |
| :--- | :--- | :--- |
| Ambigüedad de un repo con dos clones | Alta | Solo rutas, o nombre corto con coincidencia única. |
| `origin/dev` ausente en algunos repos | Alta | Verificar ref y listar ramas disponibles. |
| Tipo de rama heredado de la fase del ticket | Alta | `--type` explícito. |
| `remove --force` destruyendo trabajo sin commitear | Alta | No implementar `remove`. |
| Gate de credenciales de Plane para un comando git | Media | Ubicarlo fuera del CLI. |
| Rutas relativas resueltas contra el repo | Media | Pasar absolutas. |
| Worktree huérfano al borrar la carpeta a mano | Baja | No auto-prune; documentar `git worktree prune`. |

## Tests mínimos

1. `tests/test_worktree.py` con `git init --bare` en un `TemporaryDirectory`: clonar, commit, crear `origin/dev` remoto. Assertar estado git, no stdout: layout, rama por repo, base, idempotencia, rama ocupada, base inexistente, `basename` correcto.
2. No hacer golden del efecto en filesystem: los metadatos de `.git/worktrees` no son comparables.

## Estimación

| Ubicación | Código | Tests | Extra |
| :--- | :--- | :--- | :--- |
| Script (`bin/work/`) | ~70 líneas | ~150 líneas | Documentar en `README.md` de dotfiles |
| CLI | ~90 líneas + refactor del gate | ~150 líneas | 5 puntos de documentación + goldens |

## Estado de implementación (Noviembre 2026)

Implementado y validado en producción:
1. **Script independiente:** `bin/work/plane-worktree` (permisos 0755, Python 3 stdlib pura, sin red ni dependencias de Plane).
2. **Arquitectura:** Validación pre-flight atómica en dos fases: Fase 1 valida todos los repos, existencia de ramas remotas, disponibilidad de carpetas, estado de ramas locales y preexistencia de `.worktrees` antes de realizar ninguna mutación en filesystem o git. Fase 2 ejecuta de forma atómica usando rutas absolutas.
3. **Companion en `plane-tracker`:** `plane-tracker create --branch-slug <slug>` para desacoplar títulos en español de slugs de rama en inglés, con normalización Unicode NFKD en `cmd_tickets_write.py`.
4. **Pruebas:** 17 tests unitarios en `tests/test_worktree.py` usando repositorios remotos bare efímeros en `tempfile`. Integrado en la suite de regresión paralela `tests/run_parallel.py`.
