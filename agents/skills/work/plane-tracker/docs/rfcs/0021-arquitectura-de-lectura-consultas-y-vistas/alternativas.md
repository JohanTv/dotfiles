# Alternativas evaluadas

Parte de [0021](./README.md) (versión 2).

## Descartadas

| Alternativa | Por qué se descarta |
| :--- | :--- |
| **Mantener `search` y `list` separados** | Dos comandos sobre la misma caché obligan al agente a elegir cada vez y devuelven formas distintas. El argumento de coste (referencias y regla externa) deja de pesar porque la herramienta no está en producción. Los propósitos ("¿existe ya?" frente a "muéstrame mi trabajo") se separan con flags y valores por defecto, no con comandos. |
| **Dar filtros a `search`** (`--mine`, `--open`) y dejar `list` | Duplica la selección en dos funciones (viola "una sola fuente de verdad") y deja `list` sin texto. Contradice la decisión 0019, que ubicó los filtros en `list`. |
| **`ticket list` / `ticket search` (grupo sustantivo-verbo para todo)** | Suma un token por llamada sin desambiguar nada; la raíz ya reserva los verbos de ticket y el árbol cambiaría por completo. |
| **`find` en lugar de `list`** | El 90 % de las llamadas son filtros por estado o persona, no búsquedas; `list` describe mejor el caso común. |
| **Texto posicional (`list "texto"`)** | Obliga a adivinar si `197` es texto o ticket; con `--text` el ID va solo en `get`. **Cerrada por el dueño.** |
| **Un lenguaje de consultas / constructor de SQL genérico** | Las tablas tienen formas y costes distintos; un motor genérico escondería el coste real y añadiría una superficie que nadie necesita. |
| **Una jerarquía `View` con clase base y registro dinámico** | Una vista son metadatos y dos funciones; la herencia no aporta nada y esconde el flujo. El registro es una tabla. |
| **Fundir `report time`, `flow` y `worklog check` en una consulta** | Fuentes y costes distintos: 0 llamadas, N llamadas por ticket, auditoría contra Plane. Comparten alcance, cobertura, sobre y errores, no la consulta. |
| **JSON por defecto (sin `--json`)** | Rompería el uso humano y la regla vigente de `--json` global; los agentes lo piden explícitamente. |
| **Dejar la cobertura solo en stderr** | P5 dependería de que alguien lea stderr; un agente que parsea `--json` no la vería. |
| **Mover `worklog check` a `report`** | Es una auditoría (código 1 o 3, N llamadas a Plane), no un agregado de lectura. |
| **Retirar `list` y dejar `search` único (alias)** | `list` es un verbo del ticket de primer nivel y el caso común. |
| **Migrar solo lo que se toca (sin vocabulario común)** | Sin un contrato único la deriva reaparece con la siguiente vista; y como no hay producción que proteger, el coste de renombrar una vez es bajo. |

## Evaluadas por la revisión adversarial

| Alternativa | Estado y razón |
| :--- | :--- |
| **Abstracción mínima con pruebas de aptitud** (~12 módulos: vocabulario, cobertura, sobre, alcance, errores, vistas como funciones, 7 pruebas) | **Descartada por decisión del dueño** (quiere la versión completa). Conserva las cuatro garantías centrales y es la salida si el coste de mantenimiento de la completa resultara excesivo. |
| **Mover la guarda de duplicados a `create`** (`create --check` o la guarda actual ampliada a todos los proyectos) | **Abierta.** Eliminaría la regla de Momento Cero y su coste en tokens en cada intención de trabajo. Se evalúa con la medición de tokens ya hecha (decisión 11 del README) y con el endpoint de búsqueda del workspace como primer filtro ([`hechos-de-la-api.md`](./hechos-de-la-api.md)). No es excluyente con este RFC. |
| **Salida columnar o por líneas (NDJSON) para listas largas** | **Abierta.** Reduce tokens en listas grandes; la industria usa selección de campos y plantillas de salida. Se decide con la medición de tokens. |
| **Modo conciso y detallado** (o `--fields`) | **Abierta.** Se rechazó `--fields` por añadir una decisión al agente; un modo conciso fijo por vista (como la vista breve del Momento Cero) no lo hace. Se decide con la medición. |
| **Usar la búsqueda de texto del propio Plane** (`issues/search/`) en lugar del FTS local | **Descartada para `list --text`:** devuelve máximo 10 resultados sin estado ni grupo ni prioridad (no puede decir si un duplicado está cerrado), y gasta una petición del presupuesto de tasa. **Útil** como primer filtro barato de una guarda de duplicados en `create`. |
| **Pocas pruebas de aptitud, no 13 a 15** | **Aceptada en parte:** la guía de arquitectura evolutiva recomienda pocas y automatizadas; se sustituyen las de AST frágil (F13) por pruebas de registro y se añaden F14 y F15, que son propiedades, no análisis de código. |
