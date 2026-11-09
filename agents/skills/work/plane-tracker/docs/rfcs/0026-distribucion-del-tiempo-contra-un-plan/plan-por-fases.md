# Plan por fases del RFC 0026

Documento de apoyo del [RFC 0026](./README.md). No lleva front-matter. Describe **qué se cambia, en qué orden y cómo se comprueba**. Nada de esto está implementado mientras el RFC no pase a `implementado`. Rutas relativas a `scripts/plane_cli/` salvo indicación.

Esfuerzo total estimado sin la Fase 4: **4 a 5 días** de trabajo.

## Orden y dependencias

```
Fase 0 (decisiones) ─► Fase 1 (higiene) ─► Fase 2 (esquema y registro) ─► Fase 3 (reporte) ─► Fase 5 (docs)
                                                                                    └────────► Fase 4 (diferida)
```

Las Fases 2 y 3 son aditivas respecto al contrato `plane-tracker/1` (decisión [0025](../../decisions/0025-contrato-json-de-lectura.md)): no se quita ni se renombra ningún campo existente.

## Fase 0 · Decisiones (0,5 día)

Cerrar por escrito, en la cabecera del RFC o en un ADR, las decisiones **[PENDIENTE]**. Cada una con su valor por defecto si la persona no responde:

| # | Decisión | Valor por defecto |
| :-: | :--- | :--- |
| 1 | ¿Las filas `agent:*` de larga duración cuentan como tiempo humano? | No: se muestran aparte |
| 2 | Clasificación derivada en lectura o campo persistido | Derivada en lectura (D2) |
| 3 | Preventas y administración | `overhead` propio |
| 4 | `[SPIKE]` y `[QA]` | `aprendizaje` y `feature` |
| 5 | ¿Se autoriza `comment edit` para corregir filas ya publicadas en Plane? | No: clasificar solo en lectura |
| 6 | `capacity_bucket` | Se mantiene como eje de comportamiento |
| 7 | Jornada base para la cobertura | 480 min por día |
| 8 | Semáforos | Desviación neutra, sin color |
| 9 | Dónde se publica el plan | Solo `targets.json` local y el `CLAUDE.md` personal |
| 10 | Retiro de `phase` y `role` | Diferido hasta `plane-tracker/2` |
| 11 | Herramientas y dotfiles propios | `deuda` si sirven al equipo; `aprendizaje` si son exploración personal |

**Criterio de salida:** las 11 filas tienen respuesta escrita y el RFC pasa a `propuesto` o `aceptado`.

## Fase 1 · Higiene de datos (0,5 día)

**Objetivo:** que los números que verá el reporte nuevo no arrastren errores de clasificación evidentes.

Tareas:
1. Aplicar la decisión 1 a las filas `agent:*` (mostrar aparte o reclasificar como humano).
2. Con la decisión 5 afirmativa: `comment edit` uno a uno sobre las filas mal clasificadas, mostrando el cambio antes de aplicarlo. Con la decisión 5 negativa: dejarlas y cubrirlas en la Fase 3 con una lista de overrides locales.
3. Reconciliar el default de `phase` (el `CREATE TABLE` en `db.py` y `DEFAULTS` en `worklog_sync.py` deben coincidir).
4. Documentar en `worklog check` qué fuente manda cuando `duration_minutes` y el intervalo divergen.

**Riesgos:** editar comentarios publicados. **Mitigación:** una fila a la vez, con confirmación, sin automatizar.

**Aceptación:**
- `plane-tracker report time --offline --all-projects --json | jq '.summary.by_capacity'` muestra `coordination` solo con reuniones y coordinación reales.
- `plane-tracker worklog check` sin diferencias nuevas.

**Rollback:** los comentarios editados se vuelven a editar; la base se reconstruye con `report time --refresh`.

## Fase 2 · Esquema y registro (1 a 1,5 días)

**Objetivo:** poder declarar una clase y que viaje con el comentario.

Tareas:
1. `db.py`: `ALTER TABLE worklogs ADD COLUMN work_class TEXT` (nullable, sin valor por defecto), con la guarda de migración que ya usa el módulo.
2. `worklog.py` (parseo del bloque oculto y upsert) y `worklog_sync.py`: leer y escribir `work_class` opcional. En `DEFAULTS` **no** se añade `work_class`: ausente significa "no declarado".
3. Bloque oculto: esquema **2.3**, aditivo (campo opcional `work_class`); los comentarios 2.2 siguen siendo válidos.
4. `cmd_comment.py` y `cmd_comment_ops.py`: flag `--class` con sus valores válidos definidos **en un solo lugar** (hoy `capacity_bucket` está duplicado en tres). En un ticket paraguas `OPS`, `--class` es obligatorio y `comment add` falla sin él. En un ticket de proyecto es opcional (override).
5. `vocabulary.py`: registrar el campo y su proveniencia.

**Aceptación:**
- Una base creada con el esquema viejo migra sin pérdida y las filas antiguas leen `work_class = NULL`.
- `comment add` sobre un paraguas sin `--class` termina con error y mensaje claro.
- `report time --refresh` reconstruye los `work_class` declarados desde los comentarios.
- Suite de pruebas y goldens verdes.

**Pruebas:** una prueba que crea una base con el esquema anterior, aplica la migración y verifica lecturas; una prueba de ida y vuelta del bloque oculto 2.3; actualización de los goldens de `comment`.

**Rollback:** la columna es nullable y las versiones anteriores la ignoran. El campo nuevo del bloque oculto lo ignoran los lectores que no lo conocen.

## Fase 3 · Reporte de asignación (1,5 a 2 días)

**Objetivo:** que `report time` compare lo registrado con el plan.

Tareas:
1. Módulo nuevo de derivación: lee `classes.json`, aplica la precedencia override > etiqueta > prefijo de fase y devuelve clase y proveniencia (`declared`, `derived`, `unclassified`). Si `classes.json` no existe, usa la tabla por defecto del RFC.
2. `query_time.py`: `summary.allocation` con la forma descrita en el RFC. Solo cuenta `worker_type = human`, sobre la unión de intervalos; lo `agent:*` va a `agent_minutes`.
3. `render_time.py`: bloque `ASIGNACIÓN` con ingeniería, overhead con desglose, capacidad efectiva, cobertura, `sin clasificar` y agentes aparte; desviación con flecha y sin color; sin desviación cuando la muestra es menor al mínimo. El multiplicador de esfuerzo sale del bloque principal o se renombra a "solape de intervalos".
4. `~/.config/plane/targets.json` con esta forma, validada al leer (si falta, el bloque se omite y se avisa; no hay valores incrustados en el código):
   ```json
   {
     "version": 1,
     "engineering": { "feature": 50, "soporte": 30, "deuda": 15, "aprendizaje": 5 },
     "day_base_minutes": 480,
     "min_engineering_minutes_conclusive": 1200,
     "tolerance": { "feature": 5, "soporte": 5, "deuda_hours": 2, "aprendizaje_hours": 2 }
   }
   ```
   Los porcentajes de `engineering` deben sumar 100; si no, error claro.
5. `vocabulary.py`: notas `allocation_not_conclusive` y `unclassified_hours`.

**Aceptación:**
- `plane-tracker report time --offline --json` incluye `summary.allocation` y los campos existentes no cambian.
- Los minutos de `engineering` más `overhead` más `unclassified_minutes` suman los minutos humanos del reloj (el reporte lo verifica y lo imprime si no cuadra).
- El maquetado del RFC se reproduce con datos de ejemplo en un golden estable.
- Lo no clasificado aparece como `sin clasificar` y **no** se reparte entre las otras clases.

**Pruebas:** golden de consola y de JSON con y sin `targets.json`; casos de clase por override, por etiqueta, por prefijo, en conflicto, sin clase; solape humano-agente; muestra menor al mínimo.

**Rollback:** el bloque nuevo es aditivo; si falla, se desactiva retirando `targets.json` y el reporte vuelve a su salida anterior.

## Fase 4 · Ventana móvil y proyección (diferida)

No se empieza hasta tener al menos 3 semanas registradas. Alcance previsto: ventana móvil de 4 semanas, proyección de horas de feature que faltan para el plan al cierre de la semana, alerta cuando el overhead supera un umbral configurable. Se abrirá como RFC propio con datos reales en la mano.

## Fase 5 · Documentación (0,5 día)

Tareas:
1. `docs/principles.md`: añadir **P6 · Distribución declarada** (texto en el RFC, sin porcentajes) y una fila en las tensiones si procede.
2. `SKILL.md`: sustituir la lista de baldes del apartado de registro por las clases y añadir la regla "en paraguas, `--class` obligatorio; si hay conflicto, preguntar".
3. `~/.claude/CLAUDE.md` (personal, fuera del repo): añadir el plan de distribución, la base de cálculo sobre ingeniería y el uso de `--class` en paraguas.
4. `references/MATRIZ_TAXONOMIA_Y_TICKETS_PARAGUAS.md` y `references/ESTRATEGIA_GESTION_TI_Y_WORKITEMS.md`: retirar sus metas por balde y apuntar a este RFC. Reconciliar `reporte-ideal.md` del RFC 0005.
5. Regenerar el índice: `python3 scripts/docs_index.py`. `tests/test_docs.py` falla si queda desfasado.

**Aceptación:** una sola taxonomía de distribución documentada; ninguna meta contradictoria en `references/`; `tests/test_docs.py` verde.

## Resumen de impacto por archivo

| Archivo | Cambio | Contrato |
| :--- | :--- | :--- |
| `db.py` | Columna `work_class` nullable; reconciliar default de `phase` | Aditivo |
| `worklog.py`, `worklog_sync.py` | Leer y escribir `work_class` opcional; bloque oculto 2.3 | Aditivo |
| `cmd_comment.py`, `cmd_comment_ops.py` | Flag `--class`; obligatorio en paraguas; `choices` en un solo sitio | CLI: `comment add` en paraguas exige clase |
| `query_time.py` | `summary.allocation` | Aditivo |
| `render_time.py` | Bloque `ASIGNACIÓN`; multiplicador renombrado o retirado | Cambia el texto de consola |
| `vocabulary.py` | Campo y notas nuevas | Aditivo |
| Módulo nuevo de derivación | Tabla fase/etiqueta → clase | Nuevo |
| `tests/` y `tests/golden/` | Goldens de `comment` y `report`; pruebas de migración y derivación | — |
| `~/.config/plane/targets.json`, `classes.json` | Nuevos, locales | Nuevo |
| `docs/principles.md`, `SKILL.md`, `references/`, `CLAUDE.md` personal | Ver Fase 5 | Documental |

## Lo que queda explícitamente fuera

Retirar `capacity_bucket`, `phase` y `role`; subir a `plane-tracker/2`; reescribir comentarios publicados; ventana móvil y proyección. Cada uno tiene su motivo en el README (D6).
