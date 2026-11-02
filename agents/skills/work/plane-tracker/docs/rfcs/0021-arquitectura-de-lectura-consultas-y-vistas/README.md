---
id: "0021"
title: Arquitectura de lectura - modelo de consulta, vistas y contrato de salida
status: propuesto
created: 2026-11-02
summary: Un modelo común (alcance, cobertura, almacenes, consultas, vistas y sobre JSON versionado) para listar, buscar y reportar, con los principios convertidos en pruebas de arquitectura; funde `search` en `list`. Versión 2, tras la revisión adversarial.
---

# 0021 · Arquitectura de lectura: modelo de consulta, vistas y contrato de salida

- **Área:** todos los comandos de lectura (`list`, `search`, `get`, `report*`, `worklog check`, `labels`, `projects`, `whoami`), el contrato de salida y de errores de toda la herramienta, y la regla externa que cita `plane-tracker search`.
- **Principios:** [`principles.md`](../../principles.md). Cómo se hacen cumplir: [`principios-y-pruebas.md`](./principios-y-pruebas.md).
- **Contexto de uso:** la herramienta no está en producción ni se comparte; se puede romper compatibilidad. El usuario principal es un agente de IA, así que pesan la economía de tokens, los nombres inequívocos, la salida predecible y los errores con pista de corrección.
- **Versión:** 2. La primera versión se sometió a una [revisión adversarial](./revision-adversarial.md) (3 bloqueantes, 25 hallazgos) y la segunda a una **validación contra el código y la API real de Plane** (solo lectura; resultados en [`hechos-de-la-api.md`](./hechos-de-la-api.md) y en el registro de la revisión, que añade 12 hallazgos más).
- **Alcance elegido por el dueño:** el modelo **completo** (registro de vistas, almacenes y consultas separados, render por vista, pruebas de aptitud y contrato de errores universal).

## Documentos de esta carpeta

| Documento | Contenido |
| :--- | :--- |
| [`hechos-de-la-api.md`](./hechos-de-la-api.md) | Lo que la API real devuelve y no devuelve (paginación, filtros ignorados, límite de tasa, 403), verificado con GET. |
| [`modelo-de-consulta.md`](./modelo-de-consulta.md) | Las piezas, el **contrato de adquisición**, la regla de cobertura por vista, los invariantes y las capas. |
| [`contrato-json.md`](./contrato-json.md) | Esquema `plane-tracker/1`: sobre, vocabulario por familia, registro de notas y de errores, códigos de salida, evolución. |
| [`arbol-de-comandos.md`](./arbol-de-comandos.md) | Árbol objetivo, matriz de dimensiones y controles por vista, qué comandos usan el sobre, `sync`. |
| [`principios-y-pruebas.md`](./principios-y-pruebas.md) | Cada principio, su mecanismo y las 15 funciones de aptitud (F1-F15). |
| [`plan-de-migracion.md`](./plan-de-migracion.md) | **El plan de implementación**: nueve fases entregables con aceptación y riesgos. |
| [`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md) | El cambio de la regla externa y cuándo ejecutarlo. |
| [`alternativas.md`](./alternativas.md) | Lo evaluado y descartado, y lo que queda abierto. |
| [`revision-adversarial.md`](./revision-adversarial.md) | Los 25 hallazgos de la revisión, los 14 de la validación contra la API real y los de la implementación de las fases 0 (V15-V22) y 1 (V23-V28), con su resolución. |

## Contexto (evidencia verificada en el código)

1. **Dos comandos para lo mismo.** `search` y `list` leen la misma caché; difieren en el orden, el límite (5 fijo frente a 30) y la salida. Combinar texto con filtro de persona o estado es imposible. `list` sin filtros es la única lectura de tickets que va a la API, contra local-first.
2. **Cuatro formas de JSON para "un ticket".** `state` es un UUID en `list` crudo y un nombre en `list --mine`; el identificador se llama `ticket_id`, `ticket`, `issue_id` o `issue`; los sobres no comparten claves.
3. **La cobertura solo va por stderr.** Un agente que lee `--json` no ve los avisos de antigüedad ni de datos parciales: P5 depende de que alguien lea stderr.
4. **La reportería no comparte nada.** `report -p`, `report flow -p` y `worklog check -p` filtran de dos maneras distintas y ninguna valida el proyecto; el periodo no es reutilizable por un comando nuevo (regla de capas).
5. **`search` tiene defectos propios:** el atajo numérico ignora el prefijo del proyecto, trunca a 5 sin decir cuántos había, y mezcla prosa imperativa con datos.
6. **La API ignora `limit` y todos los filtros de servidor del listado** (hechos verificados): las vistas de persona y fecha son siempre locales, y `list --all-projects` falla hoy con 403 en un workspace con proyectos sin acceso.
7. **La sincronización fabrica datos** (defecto [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md)) y es parcial ([0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md), [0017](../../defects/0017-sincronizacion-de-worklogs-incompleta.md)): un reporte robusto necesita arreglarlos primero (fase 4 del plan).

## Decisión propuesta

Construir **desde ya** un modelo robusto, no tres funciones sueltas, porque la deriva del contrato es lo que ya duele:

1. **Alcance (`Scope`)** validado una vez, **puro**, y devuelto dentro de la respuesta.
2. **Cobertura (`Coverage`)** obligatoria, con completitud de tres valores y una **regla de cálculo por vista**; las notas se **derivan** de ella (una sola fuente por hecho).
3. **Contrato de adquisición**: toda la red de una lectura es GET y sale de `freshness`; cada vista declara qué refresca.
4. **Almacenes de solo lectura**, **consultas** que solo leen SQLite y **vistas** como datos (nombre, dimensiones, controles, adquisición, consulta, render).
5. **Un sobre JSON versionado** (`plane-tracker/1`) con **vocabulario cerrado por familia**; el texto es un render del mismo sobre.
6. **Un contrato de errores** (código, mensaje, pista, salida) usado por todas las capas.
7. **Pruebas de aptitud** (F1-F15) que hacen cumplir los principios, con trinquete por fase.
8. **Un solo `list`** (con `--text`), `report` como grupo de vistas y `sync` para el mantenimiento con coste.

**Sustituye** lo que la decisión [0019](../../decisions/0019-filtros-de-persona-y-historial-de-asignacion.md) dijo sobre dónde viven los filtros (se fusionan en `list` junto con la búsqueda) y sobre el orden por `sequence_id`; el resto de 0019 se mantiene.

## Decisiones

| # | Decisión | Estado | Resolución |
| :--- | :--- | :--- | :--- |
| 1 | `--text` como flag | **Cerrada** (dueño) | Flag; el ID va en `get`. |
| 2 | Versión completa del modelo | **Cerrada** (dueño) | Completa, con los cambios de la revisión. |
| 3 | Cambiar la regla externa y dejarlo mapeado | **Cerrada** (dueño) | Mapeado; se ejecuta en la fase 2 con la redacción confirmada (decisión 10). |
| 4 | Modelo de adquisición | **Cerrada** (dueño, 2026-11-02) | Tabla "vista → qué refresca"; `resolve_scope` puro; `report flow` declara `source: mixed`. |
| 5 | Regla de `complete` | **Cerrada** (dueño, 2026-11-02) | Tabla por vista; notas derivadas; `complete=true` imposible con una nota `warn`. |
| 6 | Horas de otras personas | **Cerrada** (dueño, 2026-11-02) | **No existe** un flag `--all-authors` en el código ni se crea (no hay datos de otros y chocaría con P2/P3). Horas con autor nulo, excluidas de "mías" y contadas aparte; `sync` sin identidad deja de mezclar horas ajenas (error `actor_unknown`, hoy solo un aviso). |
| 7 | Valores por defecto inventados por `sync` | **Cerrada** (dueño, 2026-11-02) | Registrado como defecto [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md); prerrequisito de `report time`. |
| 8 | `report agenda` | **Cerrada** (dueño, 2026-11-02) | Fuera de este RFC: la define 0005 sobre este modelo. |
| 9 | Local-first | **Cerrada** (dueño, 2026-11-02) | Enmienda "TTL con degradación" y `--offline`; `principles.md` no se modifica hasta confirmarlo. |
| 10 | Regla de Momento Cero | **Cerrada** (dueño, 2026-11-02) | `--limit 5`, leer `coverage` antes de concluir "no hay duplicado"; **depende de la fase 1** (hoy `--all-projects` falla con 403). Evaluar `create --check`. |
| 11 | JSON compacto; límite por defecto; filas breves | **Cerrada** (dueño, 2026-11-02) | **JSON compacto**; límite por defecto **20** (la regla de Momento Cero usa 5); flag fijo **`--brief`** (control de `list`: solo `ticket`, `title`, `state`, `state_group`, `project`, sin UUID). Medido: `search --json` actual 314 tokens; sobre completo compacto 726 (2,3x); indentado 989 (+36 %); filas breves 336 (1,07x). |

Las decisiones 4 a 10 se contrastaron con el código y la API real (**confirmadas con cambios**, aplicados en esta versión) y el dueño las **cerró el 2026-11-02**, junto con la 11. No queda ninguna decisión abierta: el RFC pasa a `propuesto` y se implementa fase a fase.

## Criterios de aceptación globales

- Ninguna vista emite un resultado sin cobertura ni con campos fuera del vocabulario (lo comprueba una prueba, no una revisión).
- Las vistas de caché pasan con `PLANE_OFFLINE=1` sobre una caché envejecida, y no hacen ninguna petición que no sea GET.
- El criterio `grep` de [`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md) se cumple.
- La suite sigue verde al final de cada fase ([`plan-de-migracion.md`](./plan-de-migracion.md)) y el trinquete F15 no permite pruebas saltadas de fases cerradas.

## Relacionado

[0005](../0005-vista-personal-agenda-y-backlog/README.md) (`agenda` se construye sobre este modelo), [0019](../../decisions/0019-filtros-de-persona-y-historial-de-asignacion.md) (filtros, cobertura de historial y autoría, que este RFC generaliza), [0017](../../defects/0017-sincronizacion-de-worklogs-incompleta.md), [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) y [0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md) (datos de las horas), [0018](../../decisions/0018-eliminar-tickets-sin-destruir-horas.md) (patrón de falla cerrada).
