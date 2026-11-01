---
id: "0012"
title: Estrategia de pruebas rápidas - paralelo por procesos, servidor falso ágil y lanzador sin esperas
status: aceptado
created: 2026-10-31
summary: La suite pasó de 157 s a 97 s en secuencial y a 33-48 s en paralelo, sin tocar el código de producción ni añadir dependencias.
---

# 0012 · Estrategia de pruebas rápidas

- **Mediciones y análisis de cada palanca:** [`mediciones.md`](./mediciones.md).
- **Cómo se usa:** sección "Tests" de `ARCHITECTURE.md`.

## Contexto

La suite (263 pruebas) tardaba unos 157 s en secuencial. Se quería ejecutarla con la máquina en uso normal (navegador, varias sesiones abiertas) sin que fuera una carga molesta ni inestable.

## Decisión

1. **Servidor falso ágil y silencioso.** `serve_forever(poll_interval=0.01)` (el valor por defecto, 0,5 s, se pagaba en cada cierre) y un servidor que no imprime las conexiones cortadas a propósito.
2. **Lanzador sin esperas reales** (`tests/plane_fast.py`): ejecuta el mismo `main()` acortando a 1 s el timeout de lectura. Sustituye a una espera real de 15 s sin tocar producción ni ampliar el contrato de variables de entorno.
3. **Paralelo por procesos** (`tests/run_parallel.py`, solo biblioteca estándar): un proceso por trabajo, con su propio `HOME`/`TMPDIR` y sin variables `PLANE_*`; los módulos pesados se reparten por método; prioridad baja por defecto (`--nice 10`) para no frenar el resto de la máquina.
4. **Prueba dependiente del reloj protegida:** `test_comment` repite su escenario una sola vez, y solo si la ejecución cruza un cambio de minuto.
5. El comando secuencial (`python3 -m unittest discover -s tests`) sigue siendo la referencia y el único modo para regenerar los golden (`GOLDEN_UPDATE=1`).

## Descartado

- **Ejecutar el CLI en proceso o con hilos:** las pruebas golden validan la salida real del proceso y `TZ`, `chdir`, `os.environ` y el estado de módulos son globales.
- **Una variable de entorno solo para tests (`PLANE_REQUEST_TIMEOUT`):** amplía el contrato de entorno que documenta `ARCHITECTURE.md`.
- **Imports perezosos solo por la suite:** tocan producción por unos 40 ms por arranque.
- **Optimizar `git init` o el sembrado de caché de cada sandbox:** menos del 1 % del tiempo.
- **Instalar pytest o xdist:** rompe la regla de usar solo la biblioteca estándar.

## Consecuencias

- Meta de tiempo: unos 30-40 s en una máquina de 4 núcleos físicos; difícilmente por debajo de 25 s sin reducir la ayuda por subcomando de `test_help` ni las pausas de 1 s de la publicación de la cola.
- Criterio de aceptación aplicado: 10 ejecuciones consecutivas sin fallos, una de ellas con la CPU saturada a propósito (tardó unas 3,5 veces más por la prioridad baja, sin fallos).
- El paralelismo no sube con los hilos de forma lineal: los trabajos suman el doble de CPU que en secuencial por contención.
