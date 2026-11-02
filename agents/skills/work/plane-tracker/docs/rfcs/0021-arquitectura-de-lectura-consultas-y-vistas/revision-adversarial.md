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
| H04 | ALTO | `--all-authors` sin datos (el sync descarta lo ajeno); decisión 4 inconsistente entre documentos; `author_id` NULL. | Propuesta | se **retira** `--all-authors`; NULL se excluye de "mías" y se cuenta en `hours_unsigned`; README decisión 4 |
| H05 | ALTO | El Momento Cero cuesta más tokens y la regla ignoraba `stale`/`unavailable`/`complete`. | Propuesta | cambio-de-regla (leer la cobertura, filas breves y límite propio); medir tokens antes de afirmar |
| H06 | ALTO | `sync` fabrica valores por defecto (balde, fase, rol, horas) y el sobre los presentaría como medidos. | Aplazado | defecto [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md); prerrequisito de `report time` |
| H07 | ALTO | Vocabulario "cerrado" incompleto (flujo, comprobación, `get`, catálogos, códigos de `worklog check`). | Corregido | contrato §Vocabulario por familia; `scope` opcional en `get` |
| H08 | ALTO | `agenda` necesita persona por fuente y datos que no existen (histórico de compromisos, nombres de estado); `Scope` sin `order`. | Corregido y aplazado | `Scope` con `ticket_person`, `hours_author` y `order`; `report agenda` **sale de este RFC**: la define [0005](../0005-vista-personal-agenda-y-backlog/README.md) sobre el modelo y sus datos (decisión 8 del README) |
| H09 | ALTO | Fase 1 sin consumidor; validar `-p` con red rompe local-first; fase 2 demasiado ancha; fase 3 depende de H04/H06. | Corregido | plan-de-migracion (reordenado) |
| H10 | ALTO | El criterio `grep` vacío era falso (los propios documentos citan el comando); había menciones sin prefijo; el conteo era 14 líneas en 6 archivos. | Corregido | cambio-de-regla y plan (criterio verificable y lista completa) |
| H11 | ALTO | `renamed.py` falla (`KeyError`) con `report` como grupo; las pistas de flags no se traducen. | Corregido | plan fases 2b y 4 (tareas explícitas sobre `renamed.py`) |
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
| Cambiar la regla externa "Momento Cero" y dejarlo mapeado | **Cerrada**; se ejecuta en la fase 2b. |
| Decisiones 4 a 11 del README (H01-H05, H12, `agenda`, Momento Cero, tokens) | **Propuesta** de esta versión; pendientes de la validación contra el código y la API real y de la confirmación del dueño. |

## Alternativas que el revisor añadió

Registradas en [`alternativas.md`](./alternativas.md): abstracción mínima con pruebas de aptitud (descartada por decisión del dueño), mover la guarda de duplicados a `create`, salida columnar o por líneas, modo conciso y detallado.
