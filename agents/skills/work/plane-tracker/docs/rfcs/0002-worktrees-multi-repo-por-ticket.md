---
id: "0002"
title: Gestión de worktrees multi-repo por ticket
status: propuesto
created: 2026-10-31
summary: Script independiente que crea, por ticket, un worktree en cada repo implicado con rama y base verificadas; sin implementar.
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
| `list` / `remove` | Descartadas | `git worktree list` y `git worktree remove` ya existen; reimplementarlos añade superficie destructiva. |
| `README.md` generado en el padre | Descartada | Plantilla que se desincroniza; el ticket ya es la fuente. |
| `--reuse-branch` | Descartada | La semántica de git ya distingue rama libre (attach) de rama ocupada (error). |
| `--json` | Descartada | Sin consumidor máquina hoy. |
| `--no-fetch` | Se mantiene | Sin él no hay uso offline ni test determinista. |
| Extraer `branch.py` | Aplazada | Unificaría 3 sitios, pero obliga a regenerar goldens de `create` y `search`. |

## Ubicación: CLI o script

- **Grupo en el CLI** (`plane-tracker worktree add`): un solo punto de entrada, pero el comando no necesita ningún dato de Plane y hereda el gate de credenciales; solo cabe un verbo por el presupuesto de ayuda; y el alta exige 5 puntos de documentación con tests y goldens.
- **Script independiente** (`bin/work/plane-worktree`): no habla con Plane, no toca el árbol de comandos, no consume presupuesto de ayuda y se testea aislado.

**Decisión:** script independiente. La diferencia no es la lógica (es la misma), es la puerta de entrada y su precio.

## Contrato mínimo (si se implementa)

```bash
plane-worktree add TICKET DESCRIPTION REPO[=SLUG]... \
  [--type feat] [--base dev] [--dir .worktrees] [--no-fetch]
```

| Elemento | Regla |
| :--- | :--- |
| Carpeta padre | `<dir>/<TICKET>-<DESCRIPTION>`; `--dir` se resuelve contra el cwd y se imprime en absoluto. |
| Carpeta hija | `basename(git rev-parse --show-toplevel)` del repo. |
| Rama | `<type>/<TICKET>-<SLUG>`, con `SLUG` propio del repo o el `DESCRIPTION` compartido. |
| `--type` | Explícito, default `feat`. No se deriva del título. |
| `--base` | Default `dev`. Se verifica `refs/remotes/origin/<base>` antes de crear. |
| `--repo` | Ruta a un clon; un nombre suelto se resuelve contra el cwd y sus hermanos exigiendo una única coincidencia. |
| Fetch | Best-effort: si falla, aviso y se continúa con refs locales. |

Matriz de comportamiento:

| Situación | Resultado |
| :--- | :--- |
| El destino ya es un worktree de ese repo en esa rama | Aviso "ya existe", exit 0 (idempotente). |
| La rama existe y no está checkouteada | `git worktree add <dest> <rama>` (attach). |
| La rama está checkouteada en otro worktree | Error indicando esa ruta. |
| `origin/<base>` no existe | Error listando las ramas remotas disponibles. |
| El destino existe, no está vacío y no es worktree | Error, sin tocar nada. |

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

## Condición de activación

Se implementa cuando se cree un segundo worktree multi-repo a mano, o se vuelva a teclear el layout dos veces. Si no ocurre, la propuesta se descarta: el valor no está en ahorrar contexto (el ahorro estimado es de una invocación, no de una sesión), sino en no reescribir el layout y no colisionar con ramas existentes.
