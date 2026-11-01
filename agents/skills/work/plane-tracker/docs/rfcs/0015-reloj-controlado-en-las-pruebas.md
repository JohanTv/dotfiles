---
id: "0015"
title: Reloj controlado en las pruebas desde el lanzador, sin tocar producción
status: implementado
created: 2026-11-01
summary: Implementado. Un lanzador congela la hora real del CLI en las pruebas golden, los golden dejan de enmascarar fechas y horas, y toda lectura de la hora de producción pasa por un reloj central con un presupuesto de 0 lecturas directas.
---

# 0015 · Reloj controlado en las pruebas desde el lanzador

> **Estado: implementado el 2026-11-01** (los cuatro pasos, incluida la migración de producción al reloj central). Resultados en [Implementación y resultados](#implementación-y-resultados).

- **Contexto:** [decisión 0012](../decisions/0012-estrategia-de-pruebas-rapidas/README.md) y su [`mediciones.md`](../decisions/0012-estrategia-de-pruebas-rapidas/mediciones.md), donde se registró la bomba de fecha.

## Problema

El 2026-11-01 fallaron tres pruebas golden solo ese día: un fixture tenía una fecha fija que estaba en el futuro al escribirla. Ya se corrigió de raíz (fechas de fixtures siempre pasadas) y una prueba guarda (`tests/test_golden_support.py`) impide que vuelva a entrar una fecha de hoy o futura. Pero **las pruebas siguen dependiendo de la hora real**, y eso deja fragilidades que ese arreglo no cubre.

## Hallazgos (verificados salvo indicación)

- **La hora real se lee ~44 veces en producción**; unas 35 fuera de `config.now()`, repartidas en 12-13 archivos. Ninguna usa funciones de tiempo de SQL (`db.py` no las tiene), ni `isinstance` sobre fechas, ni `from time import`, ni `date.today`. Además hay 2 lecturas de `time.monotonic` (`api.py`), 3 sitios de `sleep` y 1 `getmtime` que no afectan a la salida.
- **Los golden no verificaban las horas de los worklogs con duración declarada.** `NOW_FIELDS` (`tests/test_golden.py`) sustituía `date`, `start_time`, `end_time` y `created_at` por un valor volátil en los escenarios `comment`, `outbox` y `errors_http`, que son los que registran con `--duration` y cuyas horas salen del reloj. **Matiz:** las pruebas de propuestas, reparto y edición (`proposals`, `split`, `comment_edit_delete`) sí comparaban `date`, `start_time` y `end_time`, porque salen de transcripts con marcas fijas; solo enmascaraban `created_at`, `edited_at` y `updated_at`. El agujero era, por tanto, solo el de la duración declarada.
- **`<HOY>` no aparece en ningún golden**: la normalización de la fecha de hoy no enmascaraba nada, salvo el caso del 2026-11-01.
- **Ventana de medianoche (sin ejecutar):** `derived_start` (`worklog.py:170-176`) escribe un aviso si `ahora − duración` cruza las 00:00 y el golden `comment` no lo contiene. Entre las 00:00 y las 00:15 la prueba debería fallar (≈1 % del día).
- **`today_placeholder` y la zona horaria (sin ejecutar):** usa la fecha local del proceso de prueba y el CLI corre con `TZ=UTC`; en horas en que el día local y el UTC difieren, pueden no coincidir.
- **Margen del circuito (sin ejecutar):** `write_circuit(opened_ago=5)` se usa unas 18 veces y supone que la prueba termina en menos de 25 s reales (el enfriamiento es de 30 s).
- **`test_comment`** depende del minuto real del reloj; hoy se repite una vez si lo cruza.
- **No confirmado:** un informe sugirió que `start_time` y `end_time` pueden separarse por un cambio de minuto por lecturas repetidas del reloj. Comprobado en `cmd_comment.py`: `start` y `end` salen de una única lectura (línea 160); la lectura de la línea 222 solo alimenta `created_at`. No se registra como defecto.

## Opciones

| Opción | Beneficio | Riesgo | Coste | Encaje con las restricciones |
| :--- | :--- | :--- | :--- | :--- |
| **A.** Módulo `clock` único y todo el código lo usa, con una prueba estructural por AST | Un solo punto de lectura | Alto: toca las marcas del worklog | 3-4 días | Cumple, pero es un refactor de golpe y sin red de seguridad (ver arriba) |
| **B.** Variable de entorno que fije la hora (`PLANE_NOW`) | Ninguno que A no dé | Alto | A más 0,5 día | **Descartada**: amplía el contrato de entorno (ya rechazado en el ADR 0012); `load_zshrc_local_if_needed` copia variables de `~/.zshrc.local`, así que un valor olvidado desplazaría en silencio las marcas de tiempo que ve quien supervisa; y detectar "estoy en pruebas" en producción es un antipatrón |
| **C.** Parchear `datetime` y `time.time` en el lanzador **antes** de importar el CLI | Cubre todos los sitios sin tocar producción; las salidas no cambian | Bajo-medio (modifica la biblioteca estándar en el proceso) | ~1 día | Cumple todo |
| **D.** `libfaketime` | Sin código | No está instalado; dependencia externa | Medio | No encaja (solo biblioteca estándar) |
| **E.** freezegun o time-machine | Conocido | No instalados; solo parchean en proceso y las golden usan subprocesos | Medio | Rechazada por la regla de biblioteca estándar; C es el mismo mecanismo en unas 25 líneas |
| **F.** Reloj desplazado (fecha fija que avanza con el tiempo real) | Avanza con el tiempo | Conserva las fragilidades de arriba; hay que compartir el desplazamiento entre procesos | Medio | Peor que congelado |
| **G.** Lo ya hecho (fechas pasadas y guarda) | Casi gratis | Deja las fragilidades de arriba | 0 | Defendible si se acepta ≈1 % de probabilidad de fallo diario |

La opción C se comprobó en una prueba de humo fuera del repositorio (Python 3.14): sustituir `datetime.datetime` por una subclase y `time.time` por una función, **antes** de que `plane_cli` haga `from datetime import datetime`, hace que `datetime.now()` (con y sin zona) y `.date()` den el instante fijado; la aritmética conserva la subclase, `fromisoformat` también y `sqlite3` acepta la subclase. No cubre `monotonic` ni `sleep`, y no hace falta: los timeouts de socket, `hang` y `delay` siguen usando tiempo real.

## Recomendación (propuesta)

**Diseño.** `tests/plane_clock.py`, con la misma filosofía que `tests/plane_fast.py`: se invoca como `python plane_clock.py <ISO> <plane.py> args...`, parchea `datetime.datetime`, `datetime.date` y `time.time`, y ejecuta `plane.py` con `runpy` normalizando `sys.argv[0]`. `Sandbox.run` antepone el lanzador y el instante. No hay variable de entorno ni bandera en producción.

- **Congelado, no desplazado.** Si una prueba necesita que pase el tiempo, lo hace de forma explícita (`sb.now += 90` entre pasos). Los ayudantes de prueba (`write_circuit`, transcripts de sesión) dejan de usar la hora real y usan `sb.now`.
- **Instante fijo:** posterior a todas las fechas de los fixtures, a mediodía y en día laborable, para evitar el aviso de medianoche.
- **No parchear `time.sleep`** todavía: sería una palanca de velocidad aparte (las pausas de 1 s de la publicación de la cola) y habría que medirla.

**Plan incremental.**

1. **Medio día.** Añadir el lanzador y usarlo solo en `test_comment`; quitar el bucle de reintento si la prueba pasa de forma determinista. Añadir una prueba por AST como trinquete: el número de sitios que leen la hora fuera de `config.now()` no puede crecer (línea base: 35).
2. **Medio día.** Extenderlo a todos los golden y **dejar de enmascarar** `date`, `start_time`, `end_time` y `created_at`. Regenerar los golden con `GOLDEN_UPDATE=1`, revisando el diff como cambio intencional: es una caracterización previa a cualquier refactor y cierra el agujero de cobertura de las horas del worklog.
3. **(Hecho, ver más abajo.) Después, y solo si molesta la duplicación (2-3 días):** migrar a `config.now()` módulo por módulo, bajando la línea base del trinquete. Las pruebas ya serían deterministas sin este paso.
4. Con el reloj congelado se pueden eliminar `today_placeholder`, la guarda `FixtureDates` basada en la fecha real (pasaría a comparar contra la constante) y, más tarde, `<TS>`, "desde las" y "abierto desde hace". En un segundo paso, porque cada eliminación cambia un golden.

**Esfuerzo (opinión):** 1-1,5 días los pasos 1 y 2; 3-4 días si se hace también el paso 3.

**Criterios de aceptación.**

- 10 ejecuciones consecutivas de `tests/run_parallel.py` sin fallos.
- Suite completa con el reloj fijado en al menos dos fechas distintas posteriores a las de los fixtures (por ejemplo 2027-01-05 y 2028-02-29), una de ellas a las 00:05.
- Una fecha igual a una del fixture sirve como prueba negativa: **no** debe dar el mismo resultado, porque `report` y las propuestas dependen legítimamente de "hoy"; eso muestra qué pruebas son sensibles a la fecha.
- `--help` idéntico y ningún cambio en `scripts/`.

## Implementación y resultados

Hecho el 2026-11-01, solo en `tests/` (`scripts/` sin ningún cambio):

- **`tests/plane_clock.py`:** parchea `datetime.datetime` (`now`, `today`, `utcnow`) y `time.time` antes de importar el CLI y ejecuta el script con `runpy`; compone con `plane_fast.py`. Rechaza un instante sin zona horaria.
- **`Sandbox`:** el CLI ve un reloj congelado por defecto (lunes 2026-11-02 a las 12:00 UTC). `advance(segundos)` lo mueve de forma explícita, `command(args)` da la línea de comando con el reloj del sandbox (para procesos lanzados con `Popen`), `write_circuit` usa `sb.now` y `Sandbox(clock=None)` usa la hora real. `PLANE_TEST_NOW=<ISO con zona>` lo cambia **solo en el arnés de pruebas**; la producción no tiene ninguna variable equivalente.
- **Golden:** dejan de enmascarar fechas y horas (solo ids al azar y latencias) y se regeneraron. Se comprobó cada línea cambiada, 61 líneas en 10 archivos: **todas son solo valores de fecha u hora**, ninguna otra parte de la salida.
- **Eliminado:** `today_placeholder`, los marcadores `<HOY>`, `<TS>`, `<HH:MM>` y "abierto desde hace <N>", y el reintento de `test_comment`.
- **Una prueba tuvo que adaptarse:** `test_killed_flush_is_resolved_after_its_lease_expires` lanzaba el CLI con `Popen` sin el lanzador, así que el proceso interrumpido escribía un lease con la hora real y el siguiente `flush`, congelado y posterior, lo veía vencido. Ahora usa `sb.command(...)`.
- **Salvaguardas nuevas** (`tests/test_golden_support.py`, `tests/test_structure.py`): el lanzador (todas las formas de leer la hora ven el instante, las lecturas repetidas son idénticas, el código de salida y el nombre del script pasan, rechaza un instante sin zona y `--help` es idéntico con y sin lanzador); el `Sandbox` (congelado por defecto, `advance` y `clock=None`, el CLI ve la fecha del sandbox); los golden no usan marcadores de fecha; las fechas de fixtures son anteriores al instante congelado; el arnés no lee la hora real; y un **trinquete por AST** que fijó en 35 las lecturas de la hora real en producción fuera de `config.now()` (bajado a 0 con el paso 3, ver abajo).

**Fragilidades que quedan resueltas:** el reintento de `test_comment` (el escenario ya no depende del minuto real), la ventana de medianoche (el instante es a mediodía), la sustitución de "hoy" en zona local frente a UTC (ya no existe) y el margen de 25 s del circuito (los ayudantes usan el reloj del sandbox).

**Resultados:**

- 10 ejecuciones seguidas del runner paralelo: 277 pruebas, 0 fallos, entre 24 y 30 s cada una.
- **Prueba negativa con otros instantes** (`PLANE_TEST_NOW`): con 2027-01-05 a las 12:00 fallan 9 pruebas golden y con 2028-02-29 a las 00:05 fallan 10; **solo golden**, el resto de la suite (unitarias, cola, transporte, circuito) pasa en ambas. Los golden contienen el instante congelado (por ejemplo, "Plane no responde desde las 12:00", que a las 00:05 dice 00:05), así que **el criterio original "el mismo resultado en dos fechas" no se cumple ni debe cumplirse**; lo que se verifica es que ninguna prueba depende de la fecha real y que el resultado depende solo del instante congelado.
- **Error en la primera medición:** el runner descartaba `PLANE_TEST_NOW` junto con el resto de las variables `PLANE_*`, así que las dos primeras ejecuciones con otra fecha corrieron en realidad con el reloj por defecto y pasaron todas, sin probar nada. Se detectó porque el resultado era implausible, se corrigió el runner para dejar pasar solo esa variable y se repitió.
- `--help` idéntico con y sin el lanzador: cubierto por una prueba.

### Paso 3 (producción al reloj central): hecho el mismo día

Primero se descartó "por ahora" porque migrar cambiaba las marcas de tiempo del worklog en producción y no había red de seguridad. Con los golden ya comparando las horas exactas la red existía, y como la herramienta no está en producción y el único usuario es quien la mantiene, se hizo de inmediato.

- **`plane_cli/clock.py`** es la única fuente de la hora real. Tiene una sola primitiva, `timestamp()`, y de ella se derivan `now()` (UTC con zona), `local_now()` (local sin zona) y `local_today()`. Sustituir `timestamp` fija las tres lecturas y las mantiene coherentes entre sí. No lee variables de entorno ni tiene modo de pruebas.
- **Migrados 43 sitios:** las 35 lecturas directas (`datetime.now`, `time.time`...) y los 8 usos de `config.now()`, que se eliminó. `time.monotonic` (tiempo transcurrido) y `time.sleep` no son "la hora" y no pasan por el reloj.
- **Una lectura por función donde antes había varias.** Al registrar un worklog, `sync.py` leía el reloj tres veces para la fecha, el inicio y el fin, y `worklog.py` y `cmd_comment.py` varias veces para valores por defecto que debían ser coherentes; ahora cada función lee una vez.
- **Se llama por atributo** (`clock.now()`, nunca `from plane_cli.clock import now`), para que una prueba pueda sustituirlo; lo verifica una prueba por AST.
- **Trinquete en 0:** `tests/test_structure.py` falla si cualquier archivo, salvo `clock.py`, lee la hora real (se comprobó que detecta un `time.time()` nuevo). Se quitaron además los imports que quedaron sin usar.
- **Pruebas en proceso:** las que parcheaban `config.now` o leían la hora real usan ahora `tests/clock_support.Clock` (sustituye `clock.timestamp` y solo avanza con `advance()`): circuito, transporte, propuestas, guarda de duplicados y lecturas sin conexión. Las esperas por procesos reales de `test_outbox_flush` usan `time.monotonic`.
- **Comportamiento idéntico verificado:** los golden, que incluyen las horas exactas de los worklogs, **no cambiaron ni una línea** tras la migración.

**¿Pueden romperse en algún momento las pruebas que usaban la hora real?** Se comprobó en lugar de suponerlo. `tests/run_parallel.py --freeze <ISO>` congela la hora real del propio proceso de pruebas (con `plane_clock.py -m unittest`) y toda la suite, 284 pruebas, pasa con la hora fijada en 2027-01-05 a las 12:00, en 2028-02-29 a las 00:05 y en 2031-12-31 a las 23:59:30. Un control negativo (un instante sin zona horaria) hace fallar los trabajos, lo que demuestra que la opción se aplica y no se ignora (la primera medición con otras fechas fue inválida precisamente por eso, ver arriba).

**Limitaciones conocidas:** `time.sleep` y `time.monotonic` no se parchean (los timeouts de socket, `hang` y `delay` siguen en tiempo real, y las pausas de 1 s de la publicación de la cola se mantienen). Las aserciones con tope de tiempo real (por ejemplo, un comando debe terminar en menos de 2 o 3 s) dependen de la velocidad de la máquina, no de la fecha. El único acceso a la hora real que queda en las pruebas es el respaldo de `Sandbox.write_circuit` cuando se pide `clock=None`.

## Riesgos (con su desenlace)

- **Los golden podían cambiar al congelar el reloj.** Ocurrió, como se esperaba: 61 líneas en 10 archivos, y se comprobó que todas eran solo valores de fecha u hora.
- **Alguna prueba podía necesitar que el tiempo avanzara dentro de un único subproceso.** Resultó ser una sola (la del lease de `test_outbox_flush`) y la causa era un `Popen` sin el lanzador, no el reloj congelado. El guion de cinco procesos de `test_circuit.py` no pasa por el lanzador (usa su propio guion y la hora real) y pasa, también bajo CPU saturada.
- **Modificar la biblioteca estándar en el lanzador es magia.** Queda limitado a `tests/plane_clock.py`, está documentado en `ARCHITECTURE.md` y lo cubren pruebas del lanzador (todas las formas de leer la hora, lecturas repetidas idénticas, código de salida, nombre del script, rechazo de un instante sin zona y `--help` idéntico).

**Lo que queda de la hora real en las pruebas:** solo esperas reales (`time.sleep`, `time.monotonic`, timeouts de socket) y el respaldo `clock=None` de `Sandbox`; nada depende de la fecha del calendario, y `run_parallel.py --freeze` lo demuestra con tres instantes distintos.

## Cuándo hacerlo

Hecho. Se implementó antes del defecto [0010](../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md), de modo que las pruebas del reporte que ese arreglo toque nacen deterministas.

## Criterio de cierre

Cumplido el 2026-11-01: los cuatro pasos hechos, 10 ejecuciones seguidas sin fallos, prueba negativa con otros instantes para los golden, suite completa con la hora real congelada en tres instantes, golden sin cambios tras migrar producción y trinquete en 0.
