# Revisión adversarial (2026-11-02)

Parte de [0021](./README.md). Un revisor independiente leyó la primera versión del RFC con la consigna de romperla y la contrastó con el código. Veredicto: **aprobar con cambios** (3 bloqueantes). Este documento registra cada hallazgo, su resolución y dónde quedó atendido en la versión 2.

Estados: **Corregido** (aplicado en esta versión), **Propuesta** (la versión 2 adopta una recomendación y espera la confirmación del dueño), **Aplazado** (fuera del RFC, con documento propio), **Rechazado** (con razón).

La versión elegida por el dueño es la **completa** (modelo con registro de vistas, almacenes y consultas separados, render por vista, pruebas de aptitud y contrato de errores universal). Los hallazgos no dependen de esa elección: son errores del diseño o del plan y se corrigen igual.

## Hallazgos

| Id | Sev. | Hallazgo (resumen) | Estado | Dónde se atiende |
| :--- | :---: | :--- | :--- | :--- |
| H01 | BLOQ | "La red solo entra por `freshness`; las consultas son puras" era falso: `resolve_scope`, miembros, actor, `report flow` y los worklogs usan red. | Corregido | modelo §Contrato de adquisición; `resolve_scope` pasa a recibir catálogos ya cargados |
| H02 | BLOQ | `coverage.complete` sin regla de cálculo ni de fusión; con 0010/0017 abiertos sería siempre `null`. | Corregido | modelo §Cobertura (tabla por vista); F14; el plan hace de 0010/0017 un prerrequisito de `report time` |
| H03 | BLOQ | Notas y cobertura duplicaban hechos; F13 por AST era frágil. | Corregido | las notas se **derivan** de la cobertura (`notes_from`); F13 se sustituye por validación del registro y F14 |
| H04 | ALTO | `--all-authors` sin datos (el sync descarta lo ajeno); decisión 4 inconsistente entre documentos; `author_id` NULL. | Propuesta | se **retira** `--all-authors`; NULL se excluye de "mías" y se cuenta en `hours_unsigned`; README decisión 6 |
| H05 | ALTO | El Momento Cero cuesta más tokens y la regla ignoraba `stale`/`unavailable`/`complete`. | Propuesta | cambio-de-regla (leer la cobertura, filas breves y límite propio); medir tokens antes de afirmar |
| H06 | ALTO | `sync` fabrica valores por defecto (balde, fase, rol, horas) y el sobre los presentaría como medidos. | Aplazado | defecto [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md); prerrequisito de `report time` |
| H07 | ALTO | Vocabulario "cerrado" incompleto (flujo, comprobación, `get`, catálogos, códigos de `worklog check`). | Corregido | contrato §Vocabulario por familia; `scope` opcional en `get` |
| H08 | ALTO | `agenda` necesita persona por fuente y datos que no existen (histórico de compromisos, nombres de estado); `Scope` sin `order`. | Corregido y aplazado | `Scope` con `ticket_person`, `hours_author` y `order`; `report agenda` **sale de este RFC**: la define [0005](../0005-vista-personal-agenda-y-backlog/README.md) sobre el modelo y sus datos (decisión 8 del README) |
| H09 | ALTO | Fase 1 sin consumidor; validar `-p` con red rompe local-first; fase 2 demasiado ancha; fase 3 depende de H04/H06. | Corregido | plan-de-migracion (reordenado) |
| H10 | ALTO | El criterio `grep` vacío era falso (los propios documentos citan el comando); había menciones sin prefijo; el conteo era 14 líneas en 6 archivos. | Corregido | cambio-de-regla y plan (criterio verificable y lista completa) |
| H11 | ALTO | `renamed.py` falla (`KeyError`) con `report` como grupo; las pistas de flags no se traducen. | Corregido | plan fases 2 y 5 (tareas explícitas sobre `renamed.py`) |
| H12 | ALTO | `list` sincroniza por TTL, contra "las lecturas responden con lo local". | Propuesta | enmienda propuesta del principio y flag `--offline` (arbol, principios) |
| H13 | ALTO | Duplicar avisos en stderr y en `notes` cuesta el doble de tokens. | Corregido | contrato §stderr: en `--json` no se repite por stderr lo que va en `notes` |
| H14 | MEDIO | `limit` indefinido para reportes; F5 no admite `local`; "5 dimensiones" frente a 7 columnas. | Corregido | arbol (dimensiones frente a controles); principios F5/F12 |
| H15 | MEDIO | Zona horaria en `scope.period`; `flow` compara UTC con fechas locales; orden con empates; `source` varía. | Corregido | modelo §Alcance (`tz`), orden total, F7 en dos zonas |
| H16 | MEDIO | `sync_issues_cache` no devuelve estado; `cache_capped` no se puede emitir desde un acierto de caché. | Corregido | plan fase 1 (firma `(estado, as_of)`; `capped` persistido por proyecto) |
| H17 | MEDIO | `age_text`/`iso_utc` viven en `cache` (rompen F9); riesgo de ciclo `scope`↔`freshness`; F1/F9 débiles. | Corregido | modelo §Capas (mover a `timeutil`; `catalogs` cargados antes de `resolve_scope`); F1 con tabla; F9 ampliada |
| H18 | MEDIO | 53 `sys.exit` en 16 archivos; capa 1 y `errors`; faltan códigos de error de escrituras; `allow_abbrev`. | Corregido | contrato §errores (registro completo); plan (errores separados de escrituras; `allow_abbrev=False`) |
| H19 | MEDIO | `health`, `focus status`, `outbox list`, `attachment list`, `handoff`, `worklog propose`, `whoami` no entran ni se excluyen del sobre. | Corregido | arbol §Qué comandos usan el sobre |
| H20 | MEDIO | El RFC contradice la decisión 0019 sin declararlo; orden por defecto con NULL y entre proyectos. | Corregido | README §Sustituye; arbol §Orden |
| H21 | MEDIO | Pruebas "saltadas con motivo" dejan trabajo sin hacer; enmendar ARCHITECTURE antes del código. | Corregido | principios F15 (trinquete: una prueba de una fase ya cerrada no puede seguir saltada); ARCHITECTURE se enmienda por fase |
| H22 | MEDIO | `sync` (comando) frente a `sync.py` (worklogs); alcance indefinido; `report time --all-projects` irrealizable por los límites del sync. | Corregido | arbol (`sync` definido); plan (0017 como prerrequisito) |
| H23 | MEDIO | Validar el sobre en producción convierte una deriva en caída del comando. | Corregido | modelo §Sobre: valida en pruebas y degrada en producción con la nota `internal` |
| H24 | BAJO | "Único módulo con argparse fuera de `config`" era falso. | Corregido | modelo §Alcance |
| H25 | BAJO | Notas informativas constantes cuestan tokens; el remedio no llega al sobre; ID como texto sin pista. | Corregido | contrato (`hint` en avisos; informativas solo con `--verbose`; nota hacia `get`) |

## Decisiones del dueño

| Decisión | Estado |
| :--- | :--- |
| `--text` como flag | **Cerrada** (el dueño). |
| Versión completa del modelo | **Cerrada** (el dueño). |
| Cambiar la regla externa "Momento Cero" y dejarlo mapeado | **Cerrada**; se ejecuta en la fase 2. |
| Decisiones 4 a 11 del README (adquisición, `complete`, horas de otros, defecto 0022, `agenda`, local-first, Momento Cero, tokens) | **Cerradas** por el dueño el 2026-11-02, tras la validación contra el código y la API real. |

## Alternativas que el revisor añadió

Registradas en [`alternativas.md`](./alternativas.md): abstracción mínima con pruebas de aptitud (descartada por decisión del dueño), mover la guarda de duplicados a `create`, salida columnar o por líneas, modo conciso y detallado.

## Validación contra el código y la API real (2026-11-02)

Una segunda revisión independiente contrastó la versión 2 con el código y con la API real de Plane (solo GET, unas 115 peticiones; sin escrituras). Veredicto: **confirmar con cambios**. Los hechos observados están en [`hechos-de-la-api.md`](./hechos-de-la-api.md). Las decisiones 4 a 10 del README resultaron **confirmadas con cambios** (los cambios están aplicados).

| Id | Sev. | Hallazgo | Estado | Dónde se atiende |
| :--- | :---: | :--- | :--- | :--- |
| V1 | BLOQ | `list --all-projects` falla hoy: un 403 de un proyecto sin acceso termina el programa (`fail_http`); la premisa "un proyecto caído no aborta el resto" era falsa. | Corregido | defecto [0023](../../defects/0023-una-lectura-con-403-termina-el-programa.md); modelo §Frescura (alcance por `is_member`, `source_forbidden`); plan fase 1; regla de Momento Cero (solo tras la fase 1) |
| V2 | ALTO | La API ignora `limit` y todo filtro de servidor; los filtros de persona y fecha son locales; sin sincronización incremental por filtro. | Corregido | hechos-de-la-api; modelo §Contrato de adquisición |
| V3 | ALTO | Defecto 0017 mal diagnosticado: `limit=15` no hace nada; la causa es la lista fija de proyectos y una lectura de comentarios por ticket. | Corregido | defecto 0017 reescrito; plan fase 4 |
| V4 | ALTO | `complete` de `list` no puede calcularse con el TTL: falta guardar `total_count` por proyecto, que la API entrega y el código descarta. | Corregido | modelo §Cobertura; plan fase 1 |
| V5 | ALTO | `--all-authors` **no existe** en el código; los documentos lo describían como existente. | Corregido | README decisión 6, árbol, plan, principios |
| V6 | ALTO | `report flow --offline` no es viable sin reescribir `build_ticket_flow` (necesita `resolve_issue` y comentarios por red). | Corregido | modelo §Contrato de adquisición; plan fase 5 |
| V7 | ALTO | `get`/`resolve_issue` recorre el listado paginado del proyecto; existe el endpoint por identificador (1 GET). | Corregido | modelo; plan fase 3; defecto [0024](../../defects/0024-las-lecturas-piden-mas-datos-de-los-que-usan.md) |
| V8 | ALTO | Límite de tasa de unas 60 peticiones por ventana, con cabeceras que `api.py` descarta; una lectura en frío cuesta `3N + 1` GET. | Corregido | modelo (presupuesto de tasa); plan fase 1; nota `rate_budget_exhausted` |
| V9 | MEDIO | `renamed.py`: con `report` como grupo, `_report` queda inalcanzable y varias entradas lanzan `KeyError`; no basta añadir `EXAMPLES`. | Corregido | plan fases 2 y 5 |
| V10 | MEDIO | `sync.sync_remote_worklogs` (149 líneas) y `db.init_db` (148) están al borde del tope de 150; cualquier columna nueva los rompe. | Corregido | plan fases 0 y 4 |
| V11 | MEDIO | El sobre completo cuesta 2,3x en tokens que `search --json` (726 frente a 314); las filas breves cuestan 336. | Corregido | README decisión 11; contrato (filas breves); regla de Momento Cero |
| V12 | MEDIO | Numeración de decisiones y fases inconsistente entre documentos; la matriz no incluía `track` ni `worker_type`; `get` no sabía si los comentarios estaban completos; `triage` ausente del contrato. | Corregido | README, alternativas, contrato, árbol, modelo |
| V13 | BAJO | Constantes de instancia en el código público (`sync.py`, `cli.py`, `db.py`): `Scope` depende del "proyecto por defecto". | Aplazado | defecto 0009; modelo (`catalogs` lee la configuración) |
| V14 | BAJO | "53 `sys.exit` en 16 archivos" vale para `scripts/plane_cli/` (54 en 17 con `docs_index.py`). | Corregido | modelo §Errores (acotado a `scripts/plane_cli/`) |

Sin verificar aún (ver [`hechos-de-la-api.md`](./hechos-de-la-api.md)): que reasignar solo actualice `updated_at`, el máximo de `per_page` y la paginación real con muchos comentarios.

## Hallazgos de la implementación de la fase 0 (2026-11-02)

Al implementar la fase 0 contra el código, el RFC resultó ambiguo o contradictorio en los puntos siguientes. V15 a V17 se acordaron con el dueño antes de escribir código; V18 a V22 se descubrieron al escribirlo: cada uno se resolvió con el supuesto más conservador y **espera su confirmación**. V20 **no se resolvió** (necesita una decisión del dueño).

| Id | Sev. | Hallazgo | Estado | Dónde se atiende |
| :--- | :---: | :--- | :--- | :--- |
| V15 | ALTO | `envelope.build(view, scope, result)` y `notes_from(coverage, scope, result)` suponen `Scope` y `Result`, que la fase 0 no entrega (`scope.py` es de la fase 1) y la tabla de capas hace importar `scope` a `envelope`; el RFC no dice dónde vive `Result`, que F8 exige. | Corregido (acordado con el dueño) | `Result` vive en `coverage.py`; en la fase 0 el alcance es un `dict` ya resuelto (o `None` en `get`); la fase 1 lo tipa con `Scope`. |
| V16 | MEDIO | La firma `CliError(code, message, hint, exit_code)` no puede llevar `detail`, que el contrato usa en `http_error` (`detail.status`); `exit_code` es redundante con la tabla fija de salida. | Corregido (acordado con el dueño) | `CliError(code, message, hint=None, exit_code=None, detail=None)`; la salida sale del registro `vocabulary.ERRORS`; un código no registrado lanza `ValueError`. |
| V17 | MEDIO | F4 exige que todo código *emitido* esté registrado, pero en la fase 0 no se emite ninguno. | Corregido (acordado con el dueño) | F4 compara el registro de `vocabulary.py` con la decisión 0025 en ambos sentidos (campos, tipos, notas, errores, comprobación) y con los JSON reales de los golden; la parte "emitido" se activa cuando existan emisores. |
| V18 | MEDIO | El vocabulario "derivado de los JSON reales de hoy" no tiene destino para varios campos: horas (`issue_name`, `stoppers_json`, `raw_payload`, `plane_comment_id`, `created_at`, `updated_at`), ticket (`sequence_id`, `updated_by`) y `get` (`total_comments`, `comments_skipped`, que sirven para saber si los comentarios se leyeron completos); `assignment_events[].at_utc` pasa a `at` sin figurar en "Sustituye a"; `worklog check` entrega `unreachable` como contador (no lista); el contrato no enumera los nombres del `summary` de `report flow` ni define familias para `whoami`, `attachment list` y `outbox list`. | Propuesta | `vocabulary.REPLACES` y `vocabulary.DROPPED` los registran como decisión explícita y F4 comprueba que todo campo de hoy tiene destino; los resúmenes de flujo conservan los nombres vigentes; las familias de `whoami`, `attachment list` y `outbox list` quedan para la fase 3. Falta decidir si `total_comments` y `comments_skipped` pasan a `coverage.detail` (hoy se descartan). |
| V19 | MEDIO | `coverage.detail` solo enumera `history`, `text_fields`, `hours_scope`, `capped` y `legacy`, pero `source_forbidden`, `rate_budget_exhausted`, `assignment_snapshot`, el recuento que decide `complete` de `list` y la verificación de horas de `report time` necesitan dónde vivir para derivarse como notas. | Propuesta | Se añaden `forbidden`, `rate_budget_exhausted`, `assignment_snapshot`, `count_mismatch` y `hours_verified` (decisión 0025 y `vocabulary.DETAIL_KEYS`). |
| V20 | ALTO | F12 exige la nota `truncated` cuando `count < total`, pero `truncated` es `info` y las informativas solo salen con `--verbose`: por defecto un resultado recortado no lleva nota (solo `total` y `count`, que difieren), y el principio P5 pedía que lo recortado no pase en silencio. | **Abierto** | La prueba F12 solo exige `total` y `count <= limit`; la presencia de `truncated` queda sin comprobar hasta decidir si `truncated` pasa a `warn`, si se exceptúa de la regla de `--verbose` o si basta con `total` y `count`. |
| V21 | MEDIO | La tabla de `complete` tiene huecos frente a F14 (`complete: true` imposible con un `warn`): `legacy` sin filtro de persona no es `True` ni `None` ni `False`; `history_partial`, `rate_budget_exhausted` y `hours_local_only` son avisos sin fila en la tabla; "recuento no coincide" no tiene nota propia. | Propuesta | Regla genérica en `coverage.py`: `False` ante proyecto no disponible, sin acceso, recortado, presupuesto de tasa agotado o recuento distinto; `None` ante datos vencidos, `legacy` (la vista solo lo informa cuando afecta al resultado), historial parcial u horas solo locales; `True` solo si nada de eso; `report flow` convierte el historial parcial en `False`. F14 la verifica sobre todas las combinaciones de hechos. |
| V22 | BAJO | Detalles que el RFC no fija: (a) el orden de las notas "severidad y luego código" no dice cuál severidad va primero; (b) la tabla de capas dice que `errors` no importa nada del paquete, pero necesita el registro de salidas; (c) `cache_stale` necesita formatear la antigüedad (`age_text`) y `coverage` solo puede importar `vocabulary`; (d) `scope` del sobre solo aparece en un ejemplo, sin enumerar sus claves ni decir si los controles van en él; (e) la tabla de F1 no dice desde qué fase se aplica cada fila a los `cmd_*`; (f) qué hace el sobre cuando `complete` es `true` y detecta deriva. | Propuesta | (a) avisos antes que informativas; (b) `errors` importa `vocabulary`; (c) `coverage` importa `timeutil`; (d) `SCOPE_KEYS` enumerado y los controles fuera del sobre salvo `limit`; (e) las filas de `cmd_read`, `cmd_report` y `cmd_sync` rigen desde las fases 3, 5 y 6; (f) se degrada a `None` junto con la nota `internal`. Todo queda en la decisión 0025 y en la tabla `DEPENDENCIES` de `tests/test_architecture.py`. |
