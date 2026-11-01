---
id: "0015"
title: Reloj controlado en las pruebas desde el lanzador, sin tocar producción
status: propuesto
created: 2026-11-01
summary: Congelar la hora real en un lanzador de pruebas (parchear datetime y time.time antes de importar el CLI) para que las pruebas golden no dependan de la fecha ni de la hora.
---

# 0015 · Reloj controlado en las pruebas desde el lanzador

- **Contexto:** [decisión 0012](../decisions/0012-estrategia-de-pruebas-rapidas/README.md) y su [`mediciones.md`](../decisions/0012-estrategia-de-pruebas-rapidas/mediciones.md), donde se registró la bomba de fecha.

## Problema

El 2026-11-01 fallaron tres pruebas golden solo ese día: un fixture tenía una fecha fija que estaba en el futuro al escribirla. Ya se corrigió de raíz (fechas de fixtures siempre pasadas) y una prueba guarda (`tests/test_golden_support.py`) impide que vuelva a entrar una fecha de hoy o futura. Pero **las pruebas siguen dependiendo de la hora real**, y eso deja fragilidades que ese arreglo no cubre.

## Hallazgos (verificados salvo indicación)

- **La hora real se lee ~44 veces en producción**; unas 35 fuera de `config.now()`, repartidas en 12-13 archivos. Ninguna usa funciones de tiempo de SQL (`db.py` no las tiene), ni `isinstance` sobre fechas, ni `from time import`, ni `date.today`. Además hay 2 lecturas de `time.monotonic` (`api.py`), 3 sitios de `sleep` y 1 `getmtime` que no afectan a la salida.
- **Los golden no verifican las marcas de tiempo del worklog.** `NOW_FIELDS` (`tests/test_golden.py:20`) y `VOLATILE_KEYS` (`tests/golden_support.py:475`) sustituyen `date`, `start_time`, `end_time` y `created_at` por un valor volátil. **Un error en las horas que registra el worklog no lo detecta ninguna prueba.** Con un reloj fijo se pueden comparar valores exactos.
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
3. **Después, y solo si molesta la duplicación (2-3 días):** migrar a `config.now()` módulo por módulo, bajando la línea base del trinquete. Las pruebas ya serían deterministas sin este paso.
4. Con el reloj congelado se pueden eliminar `today_placeholder`, la guarda `FixtureDates` basada en la fecha real (pasaría a comparar contra la constante) y, más tarde, `<TS>`, "desde las" y "abierto desde hace". En un segundo paso, porque cada eliminación cambia un golden.

**Esfuerzo (opinión):** 1-1,5 días los pasos 1 y 2; 3-4 días si se hace también el paso 3.

**Criterios de aceptación.**

- 10 ejecuciones consecutivas de `tests/run_parallel.py` sin fallos.
- Suite completa con el reloj fijado en al menos dos fechas distintas posteriores a las de los fixtures (por ejemplo 2027-01-05 y 2028-02-29), una de ellas a las 00:05.
- Una fecha igual a una del fixture sirve como prueba negativa: **no** debe dar el mismo resultado, porque `report` y las propuestas dependen legítimamente de "hoy"; eso muestra qué pruebas son sensibles a la fecha.
- `--help` idéntico y ningún cambio en `scripts/`.

## Riesgos

- **Los golden pueden cambiar** al congelar el reloj: algunas salidas con edades ("hace X") podrían pasar de `<N>` a un valor concreto. No verificado.
- **Alguna prueba podría necesitar que el tiempo avance dentro de un único subproceso** (por ejemplo, el guion de `test_circuit.py` con cinco procesos simultáneos). No se leyó ese guion.
- **Modificar la biblioteca estándar en el lanzador** es magia: debe documentarse y limitarse al lanzador de pruebas.

## Cuándo hacerlo

Antes del defecto [0010](../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) conviene considerarlo: ese arreglo toca el reporte y sus pruebas dependen de fechas, y con un reloj fijo quedarían deterministas desde el principio.

## Criterio de cierre

- Pasos 1 y 2 hechos, con los criterios de aceptación cumplidos.
- Decisión registrada sobre el paso 3 (migrar o no a `config.now()`).
