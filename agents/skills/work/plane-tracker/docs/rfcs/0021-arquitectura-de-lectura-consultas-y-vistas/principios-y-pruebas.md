# Principios, mecanismos y pruebas de arquitectura

Parte de [0021](./README.md) (versión 2). Un principio que solo vive en un documento se erosiona; aquí cada uno se convierte en un mecanismo del modelo y en una **función de aptitud** (prueba que falla si se viola). Las pruebas viven en `tests/test_architecture.py`, se escriben **antes** que los módulos que vigilan y un **trinquete** (F15) impide que una prueba de una fase ya cerrada siga saltada.

## De principio a mecanismo

| Principio ([`principles.md`](../../principles.md)) | Mecanismo en el modelo | Pruebas |
| :--- | :--- | :--- |
| **P1** visibilidad del trabajo invisible | `report time` agrega por balde de capacidad (`summary.by_capacity`, con `undeclared` aparte) junto al trabajo de ingeniería; toda fila de horas lleva `capacity`. | F10 |
| **P2** autonomía: nada se envía ni se estima | Las lecturas son solo GET y nunca escriben en Plane; ninguna vista calcula una duración que no se midió; no existe forma de ver horas de otras personas. | F6 |
| **P3** datos para quien trabaja | Alcance por defecto de las vistas personales: **el actor**; el sobre incluye lo necesario para decidir (estado, prioridad, fechas, razones). | F11 |
| **P4** carga cognitiva | Una sola vista de tickets; límite por defecto con `total` visible; salida compacta; notas informativas solo con `--verbose`; sin prosa imperativa en los datos; sin duplicar avisos por stderr. | F12 |
| **P5** gestión de expectativas / no afirmar lo no medido | `Coverage` obligatoria con completitud de tres valores y regla por vista; notas derivadas; el sobre declara el alcance resuelto y qué campos cubre la búsqueda; lo por defecto no se presenta como medido. | F3, F4, F8, F13, F14 |
| **Local-first** | Las vistas de caché leen SQLite; la red es `freshness` (GET con TTL y degradación) y `get`/`sync`; `--offline` la corta. | F5, F6 |
| **Una sola fuente de verdad** | Vocabulario único; el texto es un render del sobre; las notas se derivan de la cobertura. | F1, F9, F13 |
| **No afirmar lo que no se midió** | `complete: null` se renderiza como "no verificado"; `hours_local_only`, `history_partial` y `hours_defaulted` son notas registradas. | F8, F14 |

### Enmienda al principio local-first (confirmada por el dueño el 2026-11-02 y aplicada en `principles.md`)

Redacción vigente: "las lecturas responden con lo local y avisan su antigüedad; la red es para publicar". El modelo la **precisa**, no la contradice: *"las lecturas responden con lo local; pueden refrescarlo por TTL con un GET y degradan a lo almacenado, avisando su antigüedad, si la red falla; `--offline` las limita a lo local; la red de escritura es para publicar"*. Aplicada en [`principles.md`](../../principles.md).

## Funciones de aptitud

| ID | Qué comprueba | Cómo |
| :--- | :--- | :--- |
| F1 | Capas, ciclos y **tabla de dependencias permitidas por módulo** ([`modelo-de-consulta.md`](./modelo-de-consulta.md)); capa 1 = `config`, `clock`, `vocabulary`, `errors`. | extiende `test_structure` con la tabla como datos. |
| F2 | Cada vista declara `dims`/`controls` ⊆ vocabulario y el parser de su comando tiene flags **solo** para ellos (más una lista blanca de flags no dimensionales). | recorre `VIEWS` y el parser. |
| F3 | Todo sobre producido por los golden valida: claves ⊆ vocabulario de su familia; `schema`, `view`, `total`, `count`, `results`, `coverage`, `notes` presentes; `scope` presente salvo en `get`. | `envelope.validate` enganchado a `run_scenario` para cada JSON de los golden. |
| F4 | Todo código de nota, de error y de comprobación emitido está registrado en `vocabulary.py` y documentado en [`contrato-json.md`](./contrato-json.md), y viceversa. | compara el registro con el documento **estable** (la decisión del contrato, no el RFC). |
| F5 | Toda vista de **caché** responde con `PLANE_OFFLINE=1` sobre una caché previa **más vieja que el TTL** (si no, no probaría nada): salida 0, `coverage.source` ∈ {`cache`, `local`, `snapshot`}. Excepciones declaradas: `worklog check` (siempre red) y `get` sin instantánea. | un golden por vista con `env_set` y la caché envejecida. |
| F6 | Durante cualquier vista de lectura, `sync` y `attachment list`, el servidor falso **no recibe ningún método distinto de GET**. | el servidor falso registra los métodos (ya registra `/upload`); además un AST sobre `freshness` y los almacenes rechaza `api_request(..., method=...)` no GET. Test de `Sandbox`, no golden de texto. |
| F7 | Determinismo: mismo estado y reloj ⇒ **bytes idénticos**, también bajo dos zonas horarias distintas; orden total. | doble ejecución y comparación bajo `TZ=UTC` y otra zona. |
| F8 | No existe `Result` sin `Coverage`; `complete: None` nunca se renderiza como completo. | unitaria del constructor y del render. |
| F9 | Los `render_*` consumen **solo** el sobre: no importan `sqlite3`, `os`, `clock`, `db`, `api`, `cache`, `resolve`, `store_*` ni `freshness`, y ninguna función recibe `conn`. | AST. |
| F10 | `report time --json` incluye `summary.by_capacity` (con `undeclared`) y `by_project`; los valores `provenance: default` **no** se suman a un balde declarado. | golden con comentarios de telemetría parcial (requiere el defecto 0022 corregido). |
| F11 | Las vistas personales sin flag tienen `scope.ticket_person` o `scope.hours_author` = el actor; no existe flag para ver a otros. | golden y prueba de la matriz. |
| F12 | `count <= limit` cuando hay límite; `total` siempre presente; `count < total` ⇒ nota `truncated`. | propiedad sobre los golden. |
| F13 | **No hay dos fuentes del mismo hecho**: las notas de origen "cobertura" solo existen si la cobertura las implica, y `extra_notes` no puede usar códigos derivados. | prueba unitaria de `notes_from` y del registro (sustituye al AST de `notes.append`). |
| F14 | `complete: true` ⇒ ninguna nota `warn`. | propiedad sobre los golden y unitaria. |
| F15 | **Trinquete**: una constante `CURRENT_PHASE` en la prueba lista qué F debe estar activa en cada fase; fallar si una F de una fase ≤ `CURRENT_PHASE` está saltada. | prueba meta. |

Además se mantienen: presupuesto de ayuda (280 tokens, **medido** en cada fase que toque descripciones), tope de archivo (450) y de función (150), cero lecturas directas de la hora, y `test_docs`.

## Qué estas pruebas NO garantizan

- Que el **contenido** de un dato sea correcto (lo cubren los golden y la revisión de cada vista).
- Que Plane devuelva lo que se supone (asignados, forma de los eventos, paginación, `updated_at` al reasignar): sigue **por verificar contra una instancia real** y cada fase lo declara; los hechos observados con la API real están en [`hechos-de-la-api.md`](./hechos-de-la-api.md).
- Que el ahorro de tokens sea real: se **mide** antes de afirmarlo.
