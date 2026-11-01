# Alternativas para compartir la caché entre máquinas

Parte del [RFC 0011](./README.md). Se evalúan contra los principios y las restricciones de la herramienta: la usa cualquier persona con su propia instancia de Plane, es local-first, y la fuente de verdad de los tickets y de los worklogs publicados es Plane.

## Alternativas

| | Alternativa | Idea |
| :--- | :--- | :--- |
| A | **Plane como fuente de verdad y caché desechable por máquina** (actual) | Cada máquina reconstruye lo que necesita desde Plane. |
| B | A más **sincronización más inteligente** | Aviso de datos viejos, sincronización por antigüedad o por día, sincronización incremental por `updated_at`. |
| C | **Archivo de caché compartido** | La base SQLite en una carpeta sincronizada por el usuario (Syncthing, nube personal o un repositorio privado). |
| D | **Base de datos remota** | La caché en Postgres gestionado (por ejemplo Supabase), compartida por todas las máquinas. |
| E | **Servicio propio** | Una API que mantiene la caché y la expone a la herramienta. |

## Evaluación

| Criterio | A (actual) | B (A + sincronización) | C (archivo compartido) | D (BD remota) | E (servicio propio) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Una sola fuente de verdad | Sí | Sí | Sí, pero dos copias vivas | No: Plane y la BD pueden divergir | No |
| Local-first (funciona sin red) | Sí | Sí | Sí | No (o con caché local de la caché) | No |
| Autonomía y privacidad (P2) | Máxima | Máxima | Alta (depende del servicio de archivos) | Datos de trabajo en un tercero | Depende de dónde se aloje |
| Coste de puesta en marcha por persona | Ninguno | Ninguno | Bajo | Alto: cuenta, credenciales, migraciones | Muy alto |
| Riesgo técnico | Bajo | Bajo | **Alto**: SQLite en modo WAL no tolera sincronizadores de archivos (corrupción) | Medio: hay que portar SQL (FTS5, placeholders) y gestionar concurrencia | Alto |
| Resuelve el caso observado (reporte parcial) | No por sí sola | **Sí** | Sí | Sí, pero es desproporcionado | Sí, desproporcionado |
| Resuelve el estado que solo vive en la máquina (cola, foco) | No | No | Parcial | Sí | Sí |
| Reversibilidad | — | Alta | Alta | Baja (migración de datos y credenciales) | Baja |
| Esfuerzo | — | Bajo | Bajo (pero frágil) | Alto | Muy alto |

## Observaciones

- **Lo que de verdad falla hoy es B, no D:** el caso observado se corrige con la condición de sincronización y con un aviso (defecto 0010). Una base de datos remota resolvería un problema que no se ha demostrado.
- **C** es tentadora por barata, pero compartir una base SQLite viva por un sincronizador de archivos es una causa conocida de corrupción. Si se quisiera, sería mediante exportar e importar una instantánea (`cache export` / `cache import`), no compartiendo el archivo vivo.
- **D** solo compensa si hay estado propio de la herramienta que debe estar disponible en vivo en varias máquinas, o si varias personas necesitan una vista derivada común que Plane no ofrece. Hoy ninguna de las dos condiciones está medida.
- **Lo que ninguna alternativa evita:** publicar la cola de salida antes de cambiar de máquina, porque esos comentarios aún no existen en Plane.

## Qué se necesitaría medir antes de reabrir D

1. Tiempo real de `report --refresh` para un periodo típico (semana) contra la API.
2. Casos reales en los que el estado solo local (cola, foco) se perdió o estorbó al cambiar de máquina.
3. Si varias personas piden una vista común (agenda de equipo) que no se pueda construir leyendo Plane.
