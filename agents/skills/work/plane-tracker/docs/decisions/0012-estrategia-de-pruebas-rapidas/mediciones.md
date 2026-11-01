# Mediciones y análisis de palancas

Datos de la [decisión 0012](./README.md). Máquina: portátil con 4 núcleos físicos y 8 hilos, Python 3.14. Las pruebas se ejecutaron con `HOME` temporal y sin variables `PLANE_*`.

## Dónde se iba el tiempo (secuencial, antes de cambiar nada)

| Módulo | Tiempo | Causa |
| :--- | :--- | :--- |
| `test_golden` | ~48 s (21 pruebas, 261 llamadas al CLI) | 85 % arranque de subprocesos (0,13 s por llamada) y espera; 14 % cierres del servidor falso |
| `test_outbox` | ~30 s | **una** prueba de 15,7 s esperando un timeout real de 15 s |
| `test_outbox_flush` | ~30 s | pausas reales de 1 s por ítem publicado y cierres del servidor falso |
| `test_transport` | ~14 s | cierres del servidor falso y esperas |
| `test_offline_reads` | ~12 s | ídem |
| `test_degrade` | ~7 s | ídem |
| El resto | cada uno ≤ 2 s | — |

Total secuencial: **157 s** (263 pruebas).

## Arranque del CLI

- `plane.py --help`: 0,13 s; un intérprete vacío, 0,015 s.
- Con la caché de bytecode vacía y sin escribir bytecode (como en cada sandbox), el arranque sube a 0,63-0,84 s: de ahí el calentamiento previo del runner.
- Del arranque, `plane_cli.cli` es la mayor parte (unos 85-90 ms de 130), sobre todo la importación de `urllib`/`ssl` de `attachments`.

## Palancas evaluadas

| Palanca | Ahorro | Riesgo | Resultado |
| :--- | :--- | :--- | :--- |
| `poll_interval=0.01` en el servidor falso | unos 30 s de 157 s | nulo | **Adoptada** |
| Lanzador con timeout de 1 s para la prueba de 15 s | 30 s a 8 s en el módulo | bajo | **Adoptada** |
| Paralelo por módulo | 157 s a ~60 s | bajo | Superada por la siguiente |
| Paralelo por método en los módulos pesados | 33-48 s | medio-bajo (una prueba dependía del minuto del reloj) | **Adoptada** |
| Invocar el CLI en proceso | ~26 s de CPU | **alto** | Descartada |
| Imports perezosos | ~40-60 ms por arranque | bajo, pero toca producción | Descartada |
| Variable de entorno solo para tests | 22 s de CPU | medio (amplía el contrato) | Descartada |
| Separar suite rápida y lenta | ninguno propio | — | Descartada |
| Evitar `git init`/sembrado por sandbox | < 1 % | — | Descartada |

## Resultado

| Modo | Antes | Después |
| :--- | :--- | :--- |
| Secuencial | 157 s | 97 s |
| Paralelo (`-j 8`, `nice +10`) | — | 33-48 s |
| Paralelo con la CPU saturada a propósito | — | ~130 s |

Los trabajos paralelos suman unos 250-360 s de CPU frente a los 97 s secuenciales: la contención duplica el coste, así que un escalado lineal con los hilos no existe en esta máquina.

## Fragilidades encontradas

- **Prueba dependiente del minuto del reloj.** `test_comment` espera que dos pasos caigan en el mismo minuto; si la ejecución lo cruza, falla. En secuencial fallaba en torno al 5 % de las ejecuciones y bajo contención más. Ahora repite el escenario una vez, y solo en ese caso.
- **Puerto "muerto".** `Sandbox.dead_port` reserva y libera un puerto; con varios procesos, otro servidor falso podría recibirlo. No se vio fallar; probabilidad baja y no nula.
- **Aserciones de tiempo con tope superior** (por ejemplo, un comando debe terminar en menos de 2 o 3 s): pasaron en todas las ejecuciones, incluida la saturada, con un margen de 13 a 20 veces.
