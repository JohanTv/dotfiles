# 🛡️ Gobernanza y Principios de Diseño del CLI `plane-tracker` (`CLI_DESIGN_GUARD`)

Este documento define la arquitectura formal, ergonomía y reglas de diseño para el CLI `plane-tracker`. Toda propuesta, evolución, refactorización o adición de comandos, subcomandos y flags debe evaluarse y regirse bajo estas directrices para evitar la degradación del diseño, el acoplamiento de efectos secundarios y la sobrecarga cognitiva de usuarios y agentes de IA.

---

## 1. Filosofía: El CLI como un Lenguaje Formal

Un CLI es un lenguaje de programación específico de dominio que se evalúa mediante tokens separados por espacios. Cada comando, subcomando, flag y argumento define el modelo mental de los recursos y transiciones de estado del sistema.

La degradación del CLI ocurre de forma silenciosa por atajos o parches rápidos:
* Agregar un flag a un comando existente "por conveniencia" en vez de ubicar la acción en el dominio que posee el estado.
* Introducir efectos secundarios de mutación en comandos de lectura/consulta.
* Acoplar telemetría de esfuerzo (worklogs) con estados del ciclo de vida del ticket (bloqueos).
* Imprimir advertencias o mensajes de depuración en `stdout`, rompiendo tuberías y parsers JSON.

Un CLI robusto es **ortogonal, predecible, silencioso y respeta la economía de tokens**.

---

## 2. Los 6 Pilares Invariantes de la Arquitectura CLI

```
┌─────────────────────────────────────────────────────────────┐
│          LOS 6 PILARES INVARIANTES DE PLANE-TRACKER         │
├─────────────────────────────────────────────────────────────┤
│ 1. Separación Comando-Consulta (CQS)                        │
│    Lecturas NUNCA mutan estado; escrituras no usurpan vistas│
├─────────────────────────────────────────────────────────────┤
│ 2. Ortogonalidad y Aislamiento de Dominio                   │
│    Un comando = un dominio. Los flags no cruzan fronteras   │
├─────────────────────────────────────────────────────────────┤
│ 3. Jerarquía Gramatical Estricta                            │
│    plane-tracker <recurso> <accion> [opciones]              │
├─────────────────────────────────────────────────────────────┤
│ 4. Semántica Unix I/O y Esquemas de Envoltura               │
│    stdout: datos puros/JSON · stderr: diagnósticos · exit   │
├─────────────────────────────────────────────────────────────┤
│ 5. Economía de Tokens y Ergonomía de Agentes                │
│    Vistas concisas (6-8 líneas); límites y filtros --brief  │
├─────────────────────────────────────────────────────────────┤
│ 6. Integridad Evolutiva y Ratchets                          │
│    Compatibilidad hacia atrás; módulos delgados (<450 líns) │
└─────────────────────────────────────────────────────────────┘
```

### Invariante 1: Separación Comando-Consulta (CQS)
* **Consultas / Lecturas (`list`, `get`, `report`, `status`, `whoami`):**
  * Funciones puras contra la base de datos SQLite local o caché.
  * Deben ser inmediatas (<5ms en consultas locales), idempotentes y operar offline.
  * **Cero efectos colaterales:** Una lectura NUNCA debe encolar ítems en la outbox, mutar el servidor ni modificar el estado del ticket.
  * *Antipatrón:* `plane-tracker get T --mark-read` o `plane-tracker list --auto-sync`.
* **Comandos / Mutaciones (`update`, `comment add`, `outbox flush`, `delete`):**
  * Mutaciones explícitas de estado.
  * Devuelven el resultado de la operación y el identificador del recurso afectado.
  * Las mutaciones no deben asumir el rol de generadores de reportes agregados.

### Invariante 2: Ortogonalidad y Aislamiento de Dominio
* Cada comando pertenece a una sola entidad del dominio y gobierna únicamente el ciclo de vida de dicha entidad.
* Los flags deben parametrizar *cómo* se ejecuta la acción sobre esa entidad, no disparar acciones en dominios no relacionados.
* **El caso de `--stopper` en `comment add`:**
  * `comment add` gobierna la **telemetría de esfuerzo y bitácoras de sesión** (minutos dedicados, frente de trabajo, categoría de capacidad).
  * `update --state Pausado` gobierna la **máquina de estados y ciclo de vida del ticket** (impedimentos, bloqueos externos).
  * Acoplarlos viola la ortogonalidad: un comentario no debe asumir la responsabilidad de gestionar si el ticket está o no bloqueado, ni inventar duraciones no medidas de standby.

### Invariante 3: Jerarquía Gramatical (`plane-tracker <recurso> <acción>`)
* El CLI sigue una jerarquía gramatical consistente:
  $$\text{CLI} \longrightarrow \langle\text{recurso}\rangle \longrightarrow \langle\text{acción}\rangle \; [\text{opciones}]$$
* **Recursos (Sustantivos):** `comment`, `attachment`, `outbox`, `sync`, `report`, `focus`.
* **Acciones (Verbos estándar):**
  * Colecciones: `list`, `flush`, `drop`.
  * Elementos individuales: `get`, `add` (o `create`), `edit` (o `update`), `delete`.
* **Antipatrones descartados:**
  * Comandos planos con guion: `comment-edit`, `outbox-flush` ❌ (Usar `comment edit`, `outbox flush` ✔️).
  * Verbos invertidos: `flush-outbox`, `add-comment` ❌.
  * Flags paraguas en la raíz: `plane-tracker --add-comment ...` ❌.

### Invariante 4: Semántica Unix I/O y Esquemas de Envoltura
* **`stdout` es exclusivo para Datos:** Solo los datos solicitados o JSON estructurado van a `stdout`.
* **`stderr` es exclusivo para Diagnósticos:** Advertencias, avisos de sincronización pendiente, reintentos de red y fallbacks a SQLite van estrictamente a `stderr`.
* **Modo Máquina (`--json`):**
  * Cuando se usa `--json`, la salida en `stdout` debe ser un único documento JSON válido que respete el esquema de envoltura `plane-tracker/1`.
  * Campos obligatorios del sobre: `schema`, `view`, `count`, `total`, `coverage`, `notes`, `results`.
  * Los flags de representación (`--brief`, `--json`, `--full`) solo alteran el formato, jamás la verdad de la consulta.
* **Códigos de Salida Semánticos:**
  * `0`: Éxito.
  * `1`: Error de dominio o regla de negocio (ej. ticket no existe, fecha futura).
  * `2`: Error de sintaxis o argumentos en línea de comandos (`argparse`).
  * `3`: Instancia de Plane inaccesible (activación de fallback local).

### Invariante 5: Economía de Tokens y Ergonomía de Agentes
* Los comandos son consumidos tanto por humanos como por modelos de lenguaje en chats interactivos.
* Salidas masivas desperdician la ventana de contexto y degradan el razonamiento de los agentes.
* **Directrices:**
  * Las vistas de estado deben responder en **6-8 líneas máximo**.
  * Las listas deben acotarse por defecto (`--limit 5`).
  * Ofrecer flags como `--brief` para omitir metadata voluminosa cuando solo se requieren IDs, títulos y estados.
  * Salidas completas (historiales extensos, adjuntos) deben requerir confirmación explícita (`--full`, `--history`).

### Invariante 6: Integridad Evolutiva y Ratchets de Código
* **Compatibilidad hacia atrás:** No renombrar ni eliminar flags existentes sin ciclo formal de deprecación y RFC previo.
* **Capas delgadas de parsing:** Los módulos CLI (`cli.py`, `cmd_*.py`) solo parsean y enrutan; no contienen consultas SQL crudas ni llamadas HTTP directas.
* **Límite de tamaño de archivo (Ratchet):** Ningún archivo en `scripts/plane_cli/` puede superar el límite estricto de **450 líneas** (`MAX_FILE_LINES = 450`).

---

## 3. Protocolo de Evaluación de 5 Filtros ("Antes de agregar un flag")

Antes de proponer o codificar un nuevo flag o comando en `plane-tracker`, responde a este cuestionario de 5 filtros:

| Filtro | Pregunta de Evaluación | Condición de Aprobación | Acción ante Rechazo |
| :--- | :--- | :--- | :--- |
| **1. Pertenencia de Dominio** | ¿Esta opción pertenece intrínsecamente al sustantivo que se opera? | Modifica un atributo propio del recurso. | Mover la opción al recurso que posee el estado. |
| **2. Ausencia de Efecto Secundario** | ¿El flag dispara una mutación en otro subsistema o entidad? | Es una parametrización pura de la acción actual. | Dividir en dos comandos ortogonales independientes. |
| **3. Estado vs Telemetría** | ¿Es un cambio de estado persistente, un parámetro efímero o una métrica real? | Es un dato medible y con fuente de verdad verificable. | No crear flags para datos sintéticos o no medidos. |
| **4. Alternativa Componible** | ¿Puede lograrse combinando primitivas ortogonales existentes? | La necesidad no se cubre limpiamente con comandos actuales. | Descartar el flag; usar la composición de comandos. |
| **5. Nomenclatura Estándar** | ¿El nombre sigue las convenciones estándar de Unix? | Usa nombres estándar (`--json`, `--limit`, `--brief`, `--since`, `--force`). | Renombrar siguiendo la taxonomía del CLI. |

---

## 4. Taxonomía de Banderas en `plane-tracker`

| Patrón de Flag | Significado Semántico | Incompatible con |
| :--- | :--- | :--- |
| `--json` | Salida estructurada de sobre JSON en `stdout` | Modos de texto humano |
| `--brief` | Resumen mínimo de tokens (IDs, títulos, estados) | `--full`, `--verbose` |
| `--full` | Detalle exhaustivo del recurso (historial, comentarios) | `--brief` |
| `--limit N` | Acota el número de registros devueltos | Consultas no acotadas |
| `--all-projects` / `-A` | Amplía la consulta a todos los proyectos | Flag de proyecto único `-p` |
| `--since` / `--until` | Ventana temporal delimitada | `--week` |
| `--offline` | Consulta exclusiva contra la base de datos local SQLite | Acciones de red / sync |
| `--yes` / `-y` | Omite la confirmación interactiva en comandos destructivos | Prompt interactivo |
