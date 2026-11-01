---
id: "0015"
title: Reloj central en producción y reloj congelado en las pruebas
status: aceptado
created: 2026-11-01
summary: Toda lectura de la hora pasa por un único módulo y las pruebas golden congelan la hora desde un lanzador, sin variable de entorno en producción.
---

# 0015 · Reloj central y reloj congelado en las pruebas

Relacionado: [0012](./0012-estrategia-de-pruebas-rapidas/README.md).

## Contexto

Tres golden fallaron un día concreto porque una fecha de fixture coincidió con "hoy". La causa de fondo: producción leía la hora real en unos 44 sitios y los golden enmascaraban las horas de los worklogs, así que un error en ellas no lo detectaba ninguna prueba.

## Decisión

- `plane_cli/clock.py` es la única fuente de la hora (`timestamp()` y, derivadas de ella, `now()`, `local_now()` y `local_today()`). Se usa por atributo (`clock.now()`) para poder sustituirla, y una prueba por AST exige cero lecturas directas fuera de él.
- Las pruebas golden congelan la hora desde un lanzador (`tests/plane_clock.py`) y no enmascaran fechas ni horas. Las pruebas en proceso usan `tests/clock_support.Clock`.
- `run_parallel.py --freeze <ISO con zona>` congela además el propio proceso de pruebas: la suite debe pasar con cualquier instante.

## Descartado

- **Una variable de entorno que fije la hora.** Permitiría falsificar las marcas del worklog (un valor olvidado en `~/.zshrc.local` las desplazaría en silencio) y exige un modo de pruebas dentro de producción.
- **freezegun, time-machine, libfaketime.** No son de la biblioteca estándar y no alcanzan a los subprocesos de los golden.

## Consecuencias

- Un error en las horas del worklog rompe un golden; con otro instante, los golden fallan por diseño.
- `time.sleep` y `time.monotonic` no se congelan.
