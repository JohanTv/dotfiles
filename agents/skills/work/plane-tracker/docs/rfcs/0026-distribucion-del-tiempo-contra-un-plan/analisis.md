# Análisis del RFC 0026: evidencia, alternativas y críticas

Documento de apoyo del [RFC 0026](./README.md). No lleva front-matter. Las referencias a código son por archivo y función (los números de línea cambian). Todos los números de datos son de ejemplo (decisión [0007](../../decisions/0007-documentos-agnosticos-de-instancia.md)); los reales, con los que se verificó, están fuera del repositorio.

Marcas: **[V]** verificado leyendo código o consultando la base local (hecho por dos revisiones independientes); **[S]** juicio o suposición.

## 1. Estado actual (todo [V], salvo indicación)

### 1.1 El plan no está en ningún sitio

- `docs/principles.md` solo contiene P1–P5, sin porcentajes. Es público y agnóstico de instancia, así que un plan personal no cabe ahí.
- Hay **tres fuentes de metas** que no coinciden entre sí ni con el plan:
  1. `references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md`: seis baldes con "objetivo saludable" (`deep_work` 50–60 %, `toil_support` 15–20 %, `coordination` 10–15 %, `tooling_dx`, `research_rd` y `tech_debt_paydown` 5–10 % cada uno).
  2. `references/ESTRATEGIA_GESTION_TI_Y_WORKITEMS.md`: "tres baldes" con 50–60 / 20–25 / 15–20.
  3. [`reporte-ideal.md`](../0005-vista-personal-agenda-y-backlog/reporte-ideal.md) del RFC 0005: un maquetado con metas de 20 % y 15 % para soporte y coordinación.
- **Ningún código lee metas.** Una búsqueda de `target` en `scripts/` solo encuentra `target_date` y `target_state`. Los `50 %` que aparecen en tests y goldens pertenecen a `--split`, no al plan.

### 1.2 Qué calcula hoy `report time`

- `query_time.py` (`_summary`) devuelve minutos por día, por proyecto y por balde, más dos números de esfuerzo: reloj (unión de intervalos) y cómputo (suma de duraciones).
- `render_time.py` imprime el total de reloj, la suma por proyecto y el multiplicador de esfuerzo. No imprime porcentajes, objetivo, desvío ni ventana.
- El **multiplicador** es `cómputo / reloj`. Con una jornada de 404 min sumados sobre 400 min de reloj sale 1,01×, que viene solo de 4 min de solape entre dos filas. **Mide solape, no delegación.** Además solo se imprime en la vista semanal y si `cómputo > reloj`.
- El JSON `plane-tracker/1` tiene las claves `count, coverage, notes, results, schema, scope, summary, total, view`. `summary.by_capacity` ya existe.

### 1.3 Esquema (`~/.cache/plane/worklogs.db`, tabla `worklogs`)

- Clave primaria `(ticket_id, track, date, start_time)`.
- Columnas relevantes: `track` (texto libre), `capacity_bucket` (cerrado, 6 valores, por defecto `deep_work`), `phase` (por defecto `dev` en el código y `construction_dev` en el `CREATE TABLE`: dos defaults distintos para el mismo campo), `role` (por defecto `backend_engineer`), `worker_type` (`human` o `agent:*`), `notes`, `raw_payload`, `defaulted_json` (lista de campos que cayeron al valor por defecto).
- Los seis valores de `capacity_bucket` están duplicados como `choices` en tres sitios del CLI (`cmd_comment.py` y dos en `cmd_comment_ops.py`).
- `capacity_bucket` **también gobierna comportamiento**: `proposals.py` define `NO_PROPOSAL_BUCKETS = (toil_support, coordination)`, que `cmd_comment.py` usa para decidir si propone duración.
- Otros consumidores de `capacity_bucket`, `phase` y `role` que cualquier cambio debe respetar: `worklog.py` (parseo del bloque oculto, `corrected_metadata`, `CHECK_FIELDS` de `worklog check`), `cmd_comment_ops.py` (`propose` y `edit`), `query_time.py` (contrato), `vocabulary.py`, y los tests `test_handoff`, `test_worklog_sync`, `test_report_views`, `test_proposals` con una decena de goldens.
- `phase` y `role` ya salen en `provenance` como `default` (defecto 0022 corregido). El problema de honestidad está parcialmente resuelto; retirarlos es limpieza opcional, no requisito.
- `issues_cache` guarda `title` y `labels_csv` por ticket. Las etiquetas ya se guardan bien (defecto 0020 corregido), pero **ninguna consulta de reporte las usa**.

### 1.4 Hallazgo de datos (de la base real; cifras de ejemplo en este documento)

- Casi no hay `toil_support`. Lo que en la práctica es soporte o administración (revisiones de telefonía, firma de contratos, correcciones) está registrado como `coordination`.
- Dos tickets de naturaleza distinta (una feature y una corrección de producción) quedan ambos como `deep_work`.
- Un despliegue de una feature quedó como `coordination`.
- Una feature con etiqueta `deuda-tecnica` (prefijo y etiqueta chocan) existe de verdad: ninguna regla única la resuelve.
- Los tickets paraguas mezclan clases dentro de un mismo ticket (reunión, preventa, validación de un término de referencia).
- Hay filas con `worker_type = agent:*` cuya duración es una estimación de hitos (`proposals.py` lo avisa), no reloj humano.
- La base cubre unos pocos días, así que cualquier ventana larga es hoy irrelevante.
- Conclusión: **la mala clasificación es el principal sesgo del reporte actual**; no es un problema de presentación.

## 2. Alternativas para la clasificación

| | A. Redefinir `capacity_bucket` | B. Campo nuevo persistido en cada registro | C. Derivar siempre del ticket | **D. Derivar en lectura + override persistido (elegida)** |
| :--- | :--- | :--- | :--- | :--- |
| Precisión | Media (sigue siendo declarado) | Alta | Baja en paraguas y en conflictos | Alta |
| Fricción | Baja | Media (un flag siempre) | Cero | Baja: flag solo en paraguas o al corregir |
| Paraguas | Funciona | Funciona | **Falla** (no hay clase) | Funciona (`--class` obligatorio) |
| Datos históricos | **Mala**: los valores viejos no mapean | Backfill manual | Total y automática | Total y automática |
| Cambio de título o etiquetas | No aplica | **Congela el valor viejo** | Se refleja solo | Se refleja solo |
| Riesgo de reglas inventadas | Medio | Bajo | Alto | Bajo (tabla versionada visible) |
| Otra máquina o `--refresh` | Funciona | Funciona | Funciona | Funciona (override en el bloque oculto) |
| Rompe `NO_PROPOSAL_BUCKETS` | **Sí** | No | No | No |

La B (propuesta inicial del primer análisis) se descartó en la revisión: persistir el derivado congela el error de un default y exige migrar para corregirlo. La A rompe el comportamiento que cuelga de `capacity_bucket`.

Regla de derivación propuesta (tabla en `classes.json`, precedencia override > etiqueta > prefijo):

| Señal del ticket | Clase |
| :--- | :--- |
| Etiqueta `deuda-tecnica` | `deuda` |
| Etiqueta `bug` | `soporte` |
| Prefijo `[FEAT]`, `[RFC]`, `[INFRA]` | `feature` |
| Prefijo `[FIX]` | `soporte` |
| Prefijo `[QA]` | `feature` **[PENDIENTE]** |
| Prefijo `[SPIKE]` | `aprendizaje` **[PENDIENTE]** |
| Sin señal reconocible (por ejemplo, prefijo de módulo) | `sin clasificar` |

Medida real: en el proyecto principal la mayoría de los títulos usa prefijos de módulo en vez de prefijos de fase, y casi la mitad de los tickets no tiene etiquetas. Por eso la regla de prefijo no basta sola y `sin clasificar` debe ser un resultado visible y frecuente al principio, no una anomalía.

## 3. Alternativas para el denominador y el overhead

| Opción | Qué comunica | Problema |
| :--- | :--- | :--- |
| **Overhead como línea aparte y cifra principal sobre ingeniería (elegida)** | Honestidad sobre el reloj; la capacidad efectiva de features es `plan × (1 − overhead%)` | Hay que explicar dos números; se mitiga con una sola línea derivada |
| Overhead prorrateado entre las cuatro clases | Un único 100 % comparable | Esconde reuniones y preventas; contradice P1 |
| Overhead dentro de `soporte` | Simple | Con 33 % de overhead, soporte pasaría de 30 % a más de 60 % y se culparía a soporte |
| Denominador fijo (jornada de 40 h) | Comparable entre semanas; lo no registrado se ve | Mezcla "no registrado" con "no trabajado" |

La opción elegida incorpora la cobertura del denominador fijo como línea informativa, no como base del porcentaje.

Efecto de gestión de expectativas: con 29 % de overhead, que se cumpla el 50 % de features sobre ingeniería equivale a un 35 % del tiempo registrado. Es el dato que sostiene una conversación honesta sobre lo que cabe prometer en una semana.

## 4. Críticas evaluadas y resolución

| Crítica | Resolución |
| :--- | :--- |
| Un campo nuevo obligatorio duplica la fricción que justifican la regla de 15 minutos y las etiquetas `[FASE]` | Se acepta: la clase se deriva del título y las etiquetas, y el flag solo se exige donde no se puede derivar (paraguas). |
| Si el override vive solo en la base local, otra máquina o un `--refresh` lo pierde (RFC 0011) | Se acepta: el override viaja como campo opcional `work_class` del bloque oculto del comentario. |
| Seis baldes viejos y cinco clases nuevas son dos taxonomías | Se mantiene `capacity_bucket` para comportamiento e histórico y se documenta que el plan se mide solo con `work_class`. Renombrar `deep_work` a `feature` queda como opción, no como parte de esta iniciativa. |
| Una ventana móvil de 4 semanas con 5 días de datos engaña | Diferida; mientras tanto, día y semana se marcan "no concluyente" por debajo de 20 h de ingeniería, y por debajo de unas 10 h por semana no se muestra desvío con flecha. |
| ±5 pp de tolerancia en `deuda` y `aprendizaje` es ruido | Tolerancia en horas absolutas para esas dos clases. |
| Semáforo rojo contradice "tendencias, no puntajes" | Desviación neutra sin color. |
| El tiempo de agentes distorsiona los porcentajes | Solo cuenta `worker_type = human`; los agentes se muestran aparte. |
| Sumar duraciones solapadas infla los porcentajes | Base única: unión de intervalos de reloj para el tiempo humano. |
| Reescribir en Plane los comentarios ya publicados | Descartado (ver D6 del README). |
| Retirar `phase` y `role` ahora | Diferido: es cambio de contrato (`plane-tracker/2`). |
| Sesgo de la persona al clasificar a su favor | Se limita con default derivado, proveniencia visible y reglas versionadas; no se elimina del todo. |

## 5. Casos límite y qué hace el diseño

| Caso | Tratamiento |
| :--- | :--- |
| `[FEAT]` con etiqueta de deuda | La etiqueta gana sobre la fase si no hay override; si hay conflicto real, se pregunta al registrar y se guarda el override. |
| Hotfix `[FIX]` que la persona considera feature | Override por registro. |
| Reunión con clase mixta | Una sola clase por fila; si hay que repartirla, `--split` (ya existe). |
| Sesión que toca varios tickets | Una fila por ticket; cada una deriva su clase. |
| El ticket cambia de fase o de etiquetas | La clase derivada cambia al leer; los overrides no. |
| Tiempo sin ticket | Se registra contra un paraguas con clase declarada; no se excluye. |
| Fila sin clase derivable ni declarada | `sin clasificar`, visible en el reporte; nunca se omite del total. |
| Filas históricas anteriores a esta iniciativa | Se clasifican en lectura con la tabla; no se reescriben comentarios. |
| Filas `agent:*` | No entran en los porcentajes; se muestran aparte. **[PENDIENTE]**: si algunas deben contarse como tiempo humano. |

## 6. Higiene de datos previa a medir

Los porcentajes solo son confiables si estos puntos están resueltos (se ejecutan en la Fase 1 del [plan](./plan-por-fases.md)):

1. Decidir qué hacer con las filas `agent:*` cuya duración es una estimación.
2. Corregir las filas evidentemente mal clasificadas (soporte o administración registrados como `coordination`; despliegue de una feature registrado como `coordination`).
3. Reconciliar `phase`: el `CREATE TABLE` dice `construction_dev` y el código `dev`.
4. Definir la verdad entre `duration_minutes` y `start_time`/`end_time` cuando divergen (por ejemplo con segmentos) y validarlo en `worklog check`.
5. Aceptar que la base local no tiene histórico: hasta que acumule semanas, los porcentajes son indicativos.

## 7. Qué faltaba verificar al redactar

- Si las filas `agent:*` de larga duración eran esfuerzo del agente o tiempo humano presente. Solo lo sabe la persona.
- Cómo converge este diseño con la decisión que cierre el RFC 0014 (dónde vive la verdad del tiempo); el diseño es neutral, pero conviene revisarlo cuando se cierre.
