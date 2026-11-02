# Alternativas evaluadas

Parte de [0021](./README.md).

| Alternativa | Por qué se descarta |
| :--- | :--- |
| **Mantener `search` y `list` separados** | Dos comandos sobre la misma caché obligan al agente a elegir cada vez y devuelven formas distintas. El argumento de coste (referencias y regla externa) deja de pesar porque la herramienta no está en producción. Los propósitos ("¿existe ya?" frente a "muéstrame mi trabajo") se separan con flags y valores por defecto, no con comandos. |
| **Dar filtros a `search`** (`--mine`, `--open`) y dejar `list` | Duplica la selección en dos funciones (viola "una sola fuente de verdad") y deja `list` sin texto. Contradice la decisión 0019, que ubicó los filtros en `list`. |
| **`ticket list` / `ticket search` (grupo sustantivo-verbo para todo)** | Suma un token por llamada sin desambiguar nada; la raíz ya reserva los verbos de ticket y el árbol cambiaría por completo. |
| **`find` en lugar de `list`** | El 90 % de las llamadas son filtros por estado o persona, no búsquedas; `list` describe mejor el caso común. |
| **Texto posicional (`list "texto"`)** | Obliga a adivinar si `197` es texto o ticket; con `--text` el ID va solo en `get`. Además un posicional sin flag es ambiguo con subcomandos futuros. |
| **"Abstracción mínima": tres módulos pequeños** (`scope`, `select`, `envelope`) | Es lo que ya hay de hecho. No impide que una vista nueva olvide la cobertura, emita un campo fuera del vocabulario o toque la red: los principios siguen siendo disciplina. El modelo propuesto los convierte en estructura y en pruebas. |
| **Un lenguaje de consultas / constructor de SQL genérico** | Las tablas (`issues_cache`, `worklogs`, `state_transitions`, `assignment_events`) tienen formas y costes distintos; un motor genérico escondería el coste real y añadiría una superficie que nadie necesita. |
| **Una jerarquía `View` con clase base y registro dinámico** | Una vista son metadatos y dos funciones; la herencia no aporta nada y esconde el flujo. El registro es una tabla. |
| **Fundir `report time`, `flow`, `agenda` y `worklog check` en una consulta** | Fuentes y costes distintos: 0 llamadas, N llamadas por ticket, caché, auditoría contra Plane. Comparten alcance, cobertura, sobre y errores, no la consulta. |
| **`--fields` para elegir columnas** | Añade una decisión al agente y rompe la predictibilidad del esquema; el límite de resultados ya acota los tokens. |
| **JSON por defecto (sin `--json`)** | Rompería el uso humano y la regla vigente de `--json` global; los agentes lo piden explícitamente. |
| **Dejar la cobertura solo en stderr** | P5 dependería de que alguien lea stderr; un agente que parsea `--json` no la vería. |
| **Mover `worklog check` a `report`** | Es una auditoría (código 1 o 3, N llamadas a Plane), no un agregado de lectura. |
| **Retirar `list` y dejar `search` único (alias)** | `list` es un verbo del ticket de primer nivel y el caso común; invertir la fusión pierde el nombre correcto. |
| **Migrar solo lo que se toca (sin vocabulario común)** | Renombrar campos duele más que renombrar comandos; sin un contrato único la deriva reaparece con la siguiente vista. |
