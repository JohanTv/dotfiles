# Principios, mecanismos y pruebas de arquitectura

Parte de [0021](./README.md). Un principio que solo vive en un documento se erosiona; aquí cada uno se convierte en un mecanismo del modelo y en una **función de aptitud** (prueba que falla si se viola). Las pruebas viven en `tests/test_architecture.py` y se escriben **antes** que los módulos que vigilan (en rojo o saltadas con motivo) para que cada fase las vaya activando.

## De principio a mecanismo

| Principio ([`principles.md`](../../principles.md)) | Mecanismo en el modelo | Prueba |
| :--- | :--- | :--- |
| **P1** visibilidad del trabajo invisible | `report time` agrega por balde de capacidad (`summary.by_capacity`) junto al trabajo de ingeniería, y `report agenda` muestra el trabajo invisible de la semana. El vocabulario incluye `capacity` en toda fila de horas. | F10 |
| **P2** autonomía: nada se envía ni se estima | Las lecturas son solo GET y nunca escriben en Plane; ninguna vista calcula una duración que no se midió. | F6 |
| **P3** datos para quien trabaja | El alcance por defecto de las vistas personales es **el actor** (`report time`, `agenda`); ver lo ajeno es un flag explícito. Todo sobre incluye lo que hace falta para decidir (estado, prioridad, fechas, razones). | F11 |
| **P4** carga cognitiva | Una sola vista de tickets (menos decisiones del agente); límite por defecto con `total` siempre visible; salida compacta; sin prosa imperativa en los datos. | F12 |
| **P5** gestión de expectativas / no afirmar lo no medido | `Coverage` obligatoria con completitud de tres valores; notas con código; el sobre declara el alcance resuelto y los campos que la búsqueda cubre. | F3, F4, F8 |
| **Local-first** | Las vistas solo leen la caché; la red es `freshness` (GET de sincronización) y `get`/`sync`. | F5, F6 |
| **Una sola fuente de verdad** | El vocabulario es la única definición de un campo; el texto es un render del sobre; Plane sigue siendo la fuente del ticket y la caché declara su antigüedad. | F1, F9 |
| **No afirmar lo que no se midió** | `complete: null` se renderiza como "no verificado", nunca como completo; `hours_local_only`/`history_partial` son notas, no texto libre. | F8, F13 |

## Funciones de aptitud

| ID | Qué comprueba | Cómo |
| :--- | :--- | :--- |
| F1 | Capas e imports acíclicos; los `render_*` y `store_*` respetan sus dependencias permitidas. | extiende `test_structure.test_import_graph_is_acyclic_and_layered` con la tabla de [`modelo-de-consulta.md`](./modelo-de-consulta.md). |
| F2 | Cada vista declara `dims` ⊆ dimensiones del vocabulario, y el parser de su comando tiene flags **solo** para esas dimensiones. | recorre `VIEWS` y el parser (`command_tree`). |
| F3 | Todo sobre producido por los golden valida: claves ⊆ vocabulario, `schema`, `view`, `scope`, `total`, `count`, `results`, `coverage`, `notes` presentes. | un validador `envelope.validate` aplicado a cada JSON de los golden. |
| F4 | Todo código de nota y de error emitido está registrado en `vocabulary.py` y documentado en [`contrato-json.md`](./contrato-json.md), y viceversa. | compara el registro con el documento. |
| F5 | **Todas** las vistas de lectura responden con `PLANE_OFFLINE=1` sobre una caché previa (salida 0, `coverage.source` = `cache` o `snapshot`). | un golden por vista con `env_set` sin red. |
| F6 | Durante cualquier vista de lectura el servidor falso **no recibe ningún método distinto de GET** (ni a Plane ni al almacenamiento de adjuntos). | el servidor falso registra los métodos; la prueba falla si ve POST, PATCH, PUT o DELETE. |
| F7 | Determinismo: dos ejecuciones con el mismo estado y reloj producen **bytes idénticos**; el desempate del orden está definido. | ejecución doble y comparación. |
| F8 | No existe `Result` sin `Coverage`; `complete: None` nunca se renderiza como completo. | prueba unitaria del constructor y del render. |
| F9 | Los `render_*` consumen **solo** el sobre: no importan `db`, `api`, `cache`, `resolve` ni `store_*`. | AST sobre los módulos `render_*`. |
| F10 | `report time --json` incluye `summary.by_capacity` y `summary.by_project`; `agenda` incluye el trabajo invisible. | golden de cada vista. |
| F11 | Las vistas personales aceptan `--all-authors`/`--all-projects` solo como flag explícito; sin él, `scope.person` es el actor. | golden y prueba de matriz. |
| F12 | `count <= limit`; `total` siempre presente; `count < total` ⇒ nota `truncated`. | prueba de propiedad sobre los golden. |
| F13 | Ninguna nota de cobertura se emite como texto libre: todas vienen de `vocabulary`. | AST: los `notes.append` usan el constructor del registro. |

Además se mantienen las salvaguardas vigentes: presupuesto de ayuda (280 tokens), tope de archivo (450) y de función (150), cero lecturas directas de la hora, y `test_docs`.

## Qué estas pruebas NO garantizan

- Que el **contenido** de un dato sea correcto (eso lo cubren los golden y la revisión de cada vista).
- Que Plane devuelva lo que se supone (asignados, forma de los eventos de asignación, paginación de comentarios): sigue "por verificar contra una instancia real" y cada decisión lo declara.
- Que el ahorro de tokens sea real: se **mide** antes de afirmarlo (decisión abierta 2 de [0021](./README.md)).
