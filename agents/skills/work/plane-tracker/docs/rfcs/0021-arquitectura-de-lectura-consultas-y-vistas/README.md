---
id: "0021"
title: Arquitectura de lectura - modelo de consulta, vistas y contrato de salida
status: borrador
created: 2026-11-02
summary: Un modelo común (alcance, cobertura, consultas, vistas y sobre JSON versionado) para listar, buscar y reportar, con los principios convertidos en pruebas de arquitectura; funde `search` en `list`.
---

# 0021 · Arquitectura de lectura: modelo de consulta, vistas y contrato de salida

- **Área:** todos los comandos de lectura (`list`, `search`, `get`, `report*`, `worklog check`, `labels`, `projects`, `whoami`), futuro `report agenda` ([0005](../0005-vista-personal-agenda-y-backlog/README.md)) y el contrato de salida/errores de toda la herramienta.
- **Principios:** [`principles.md`](../../principles.md). Cómo se hacen cumplir: [`principios-y-pruebas.md`](./principios-y-pruebas.md).
- **Contexto de uso:** la herramienta no está en producción ni se comparte; se puede romper compatibilidad. El usuario principal es un agente de IA, así que pesan la economía de tokens, los nombres inequívocos, la salida predecible y los errores con pista de corrección.

## Documentos de esta carpeta

| Documento | Contenido |
| :--- | :--- |
| [`modelo-de-consulta.md`](./modelo-de-consulta.md) | Las piezas (alcance, cobertura, almacenes, consultas, vistas, sobre), sus contratos, invariantes y dónde viven en las capas. |
| [`contrato-json.md`](./contrato-json.md) | Esquema `plane-tracker/1`: sobre, vocabulario de campos, registro de códigos de nota y de error, códigos de salida, evolución. |
| [`arbol-de-comandos.md`](./arbol-de-comandos.md) | Árbol objetivo, matriz de flags por vista, qué se borra o renombra. |
| [`principios-y-pruebas.md`](./principios-y-pruebas.md) | Cada principio, el mecanismo que lo cumple y la prueba de arquitectura que lo vigila. |
| [`plan-de-migracion.md`](./plan-de-migracion.md) | Fases entregables con criterio de aceptación, archivos, golden y riesgos. |
| [`cambio-de-regla-momento-cero.md`](./cambio-de-regla-momento-cero.md) | El cambio de la regla externa que cita `plane-tracker search`, y cuándo ejecutarlo. |
| [`alternativas.md`](./alternativas.md) | Lo evaluado y descartado, con el porqué. |

## Contexto (evidencia verificada en el código)

1. **Dos comandos para lo mismo.** `search` y `list` leen la misma caché; difieren en el orden (relevancia frente a recencia), el límite (5 fijo frente a 30) y la salida. Combinar texto con filtro de persona o estado es imposible. `list` sin filtros es la única lectura de tickets que va a la API, contra local-first.
2. **Cuatro formas de JSON para "un ticket".** `state` es un UUID en `list` crudo y un nombre en `list --mine`; el identificador se llama `ticket_id`, `ticket`, `issue_id` o `issue` según el comando; los sobres (`{query,...}`, `{mode,scope,...}`, arrays pelados, `{period,...}`) no comparten claves.
3. **La cobertura solo va por stderr.** Los avisos de antigüedad y de datos parciales no están en el JSON: un agente que lee `--json` no los ve, y la afirmación "no afirmar lo que no se midió" (P5) depende de que alguien lea stderr.
4. **La reportería no comparte nada.** `report -p`, `report flow -p` y `worklog check -p` implementan el filtro de proyecto de dos maneras distintas y ninguna valida que el proyecto exista; el periodo se declara en `cmd_report` y no lo puede reutilizar un comando nuevo (regla de capas).
5. **El `search` tiene defectos propios:** el atajo numérico ignora el prefijo del proyecto (`search PRJ-2 -p OTHER` devuelve `OTHER-2`), trunca a 5 sin decir cuántos había, y mezcla prosa imperativa (consejo de rama) con datos.

## Decisión propuesta

Construir **desde ya** un modelo de lectura robusto, y no tres funciones sueltas, porque la deriva del contrato es lo que ya duele:

1. **Alcance (`Scope`)**: un objeto validado una sola vez (proyectos, persona, periodo, estado, texto, límite) que se devuelve dentro de la respuesta.
2. **Cobertura (`Coverage`)** obligatoria en todo resultado, con completitud de tres valores (sí, no, **no verificado**): P5 deja de ser disciplina y pasa a ser estructura.
3. **Almacenes de solo lectura** con cobertura declarada, **consultas** puras sobre ellos y **vistas** (`list`, `report time`, `report flow`, `report agenda`, ...) que son datos (nombre, dimensiones que aceptan, consulta, render), no código suelto en cada comando.
4. **Un sobre JSON versionado** (`plane-tracker/1`) y un **vocabulario cerrado** de campos y de códigos de nota; el texto para humanos es un render del mismo sobre, nunca otra consulta.
5. **Un contrato de errores** (código, mensaje, pista de corrección) y tabla fija de códigos de salida.
6. **Pruebas de arquitectura** (funciones de aptitud) que hacen cumplir los principios: lecturas solo GET, todas las vistas funcionan sin conexión, todo campo y toda nota están registrados, ninguna vista ignora en silencio un flag.
7. **Un solo comando `list`** (con `--text`) en lugar de `search`; `report` como grupo de vistas; `sync` para el mantenimiento con coste en peticiones.

## Decisiones abiertas (a cerrar en la revisión)

| # | Pregunta | Recomendación actual |
| :--- | :--- | :--- |
| 1 | ¿`--text` como flag o texto posicional? | Flag: evita adivinar si `197` es texto o ticket; el ID va en `get`. **Cerrada por el usuario.** |
| 2 | ¿JSON compacto o indentado? | Compacto, pero **medir** los tokens reales antes de afirmar un ahorro. |
| 3 | Límite por defecto | 20, con `total` siempre presente. |
| 4 | ¿`report time` mide por defecto solo mis horas? | Sí (P3); `--all-authors` explícito para las de otros. |
| 5 | ¿`get` entra al sobre común? | Sí, con `coverage.source` (`api` o `snapshot`) y sin `Scope` (su alcance es un ticket). |
| 6 | Nombre de la vista `report time` frente a `report hours` | `time` (coincide con el balde de tiempo; el verbo es neutro). |

## Criterios de aceptación globales

- Ninguna vista emite un resultado sin cobertura ni con campos fuera del vocabulario (lo comprueba una prueba, no una revisión).
- Todas las vistas de lectura pasan con `PLANE_OFFLINE=1` sobre una caché previa y no hacen ninguna petición que no sea GET.
- `grep -rn "plane-tracker search"` queda vacío salvo la pista de `renamed.py`.
- La suite sigue verde al final de cada fase ([`plan-de-migracion.md`](./plan-de-migracion.md)).

## Relacionado

[0005](../0005-vista-personal-agenda-y-backlog/README.md) (`agenda` se construye sobre este modelo), [0019](../../decisions/0019-filtros-de-persona-y-historial-de-asignacion.md) (filtros y cobertura de historial, que este RFC generaliza), [0017](../../defects/0017-sincronizacion-de-worklogs-truncada-a-15-tickets.md) y [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) (cobertura de las horas), [0018](../../decisions/0018-eliminar-tickets-sin-destruir-horas.md) (patrón de falla cerrada).
