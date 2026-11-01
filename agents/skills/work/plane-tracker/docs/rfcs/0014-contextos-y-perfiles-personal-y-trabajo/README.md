---
id: "0014"
title: Contextos, perfiles y fuentes de tareas intercambiables
status: borrador
created: 2026-11-01
summary: "Aplazado a propósito. Usar la herramienta en varios contextos (trabajos, personal) y con varios sistemas de tareas; la decisión abierta es dónde vive la verdad del tiempo."
---

# 0014 · Contextos, perfiles y fuentes de tareas intercambiables

> **Estado: borrador aplazado a propósito (2026-11-01).** No se va a abordar ahora; hay otras prioridades. Este documento recoge el análisis completo para retomarlo sin reconstruirlo. Los disparadores para retomarlo están en [Cuándo retomarlo](#cuándo-retomarlo).

- **Alternativas, tablas de evaluación y datos de las APIs:** [`alternativas.md`](./alternativas.md).
- **Escenarios, uno por uno:** [`escenarios.md`](./escenarios.md).
- **Defecto relacionado (real hoy):** [0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md).
- **Decisión que depende de esta:** [RFC 0011](../0011-cache-compartida-entre-maquinas/README.md) (parte de que Plane es la fuente de verdad).
- **Principios:** [`principles.md`](../../principles.md).

## Resumen

1. Hoy la herramienta está **forzada a un único entorno**: un Plane, una base local, un workspace. Cualquier otro uso (dos trabajos, otro tracker, lo personal) choca con eso.
2. Hay dos formas de verlo, y **no son la misma**:
   - **Premisa original:** la herramienta es un cliente de Plane con telemetría de tiempo, y Plane es la fuente de verdad. Para lo personal bastaría un segundo Plane.
   - **Premisa nueva (la que describió quien la usa):** la herramienta **lleva el tiempo y los reportes**; las tareas se gestionan en **otro sistema** (Plane, Jira, Linear, o un sistema propio en archivos markdown) y la herramienta es agnóstica de cuál sea.
3. Cambiar de premisa **invierte el diseño**: el núcleo pasa a ser un libro de actividad local, el ticket es una referencia, y los sistemas de tareas son integraciones opcionales por niveles.
4. **Decisión abierta y sin resolver:** dónde vive la verdad del tiempo registrado. Se analiza abajo sin decidirla.
5. Lo que sirve en cualquiera de las dos premisas: **perfiles con aislamiento físico** y corregir el [defecto 0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md).

## Terminología

Los documentos anteriores usaban "backend", que confunde. En este RFC:

| Término | Significa |
| :--- | :--- |
| **Fuente de tareas** | El sistema donde viven los tickets o tareas: Plane, Jira, Linear, Todoist, GitHub Issues o archivos markdown. Antes "backend". |
| **Libro de actividad** | El registro de lo que se hizo y cuánto tiempo: worklogs, baldes de capacidad, sesiones medidas. Es la parte que ya es agnóstica del código actual. |
| **Referencia de ticket** | Una clave y, opcionalmente, un título (`PROJ-123`). Basta para registrar tiempo sin consultar la fuente. |
| **Contexto** | Un ámbito de vida o de trabajo con sus propias reglas: un empleo, lo personal. |
| **Perfil** | La configuración y los datos aislados de un contexto: directorio, base de datos, credenciales, baldes y fuente de tareas. |
| **Integración** | La conexión opcional con una fuente de tareas, en tres niveles (ver abajo). |

## Necesidad

Una misma persona quiere usar la herramienta en varios mundos, a veces el mismo día y en la misma máquina:

- **Trabajo:** una instancia de Plane de la organización, con varios proyectos. Podría haber **más de un trabajo**, con el mismo sistema o con distintos (Plane, Linear, Jira).
- **Personal:** áreas como idiomas (con varias tareas pendientes), tesis, proyectos propios (incluida esta herramienta, que podría ser de código abierto) y cursos. Se quiere **tiempo y también estados**.
- **Administración personal** (pagar tarjetas, cancelar suscripciones): tareas recurrentes sin cifras que hoy viven en una herramienta de tareas personal y funcionan bien allí.
- **Métricas de la semana** que crucen todos los contextos.
- **Quien supervisa prefiere un resumen**, no los comentarios de cada ticket. Publicar el tiempo en el tracker es metadata por si algún día se lee.
- **La herramienta podría adoptarse en un trabajo** que use otro sistema de tareas, o ser el sistema que se propone.

## Restricciones

- Lo personal **nunca** puede llegar a la instancia de una organización (P2). La cola de salida publica comentarios, así que un error de contexto es una fuga.
- Lo del trabajo puede contener información de la organización (títulos de tickets): no debe acabar sincronizado con espacios personales (repositorios, nubes personales).
- El repositorio es público y los documentos son agnósticos ([0007](../../decisions/0007-documentos-agnosticos-de-instancia.md)).
- Local-first, solo biblioteca estándar, mantenedor único, árbol de comandos raíz cerrado y ayuda global sin margen (`tests/test_cli_tree.py`).

## Hallazgos que condicionan el diseño (verificados en el código)

- **No existe una costura de integración.** Las rutas `/api/v1/workspaces/...` se construyen a mano en unos quince módulos. Los módulos agnósticos (sin red) son `worklog`, `timeutil`, `proposals`, `proposal_store`, `mdhtml`, `session_clock` y `flow_metrics`; el resto habla con Plane (detalle en `alternativas.md`).
- **El worklog viaja por el transporte de Plane:** se guarda como bloque oculto en un comentario del ticket y se reconstruye desde ahí. Otra fuente de tareas exigiría que conserve ese bloque, o un almacén de worklogs aparte.
- **La base local no distingue instancias:** `projects` tiene como clave la clave de proyecto, `worklogs` no tiene workspace ni proyecto en su clave primaria, y unas 42 de 43 consultas a las tablas locales no filtran por workspace. Una columna de contexto obligaría a tocarlas todas, y olvidar una sería una fuga silenciosa.
- **Valores de una organización concreta en el código:** listas fijas de claves de proyecto en `sync.py` y `cmd_read.py`, y un workspace y un proyecto por defecto en `cli.py` ([0009](../../defects/0009-saneamiento-pendiente-de-datos-de-instancia.md)).
- **La caché no se puede reubicar por variable** (`config.py`) y la medición de sesiones de agente lee transcripts relativos a `HOME`.

## Arquitectura propuesta (si se adopta la premisa nueva)

### Capas

1. **Libro de actividad (núcleo).** Local y sin red: worklogs, baldes, sesiones medidas, fusión de intervalos, métricas de flujo y reportes. Ya existe casi entero.
2. **Referencias de ticket.** Una clave más un título opcional, calificada por el perfil (`perfil:CLAVE-N`) para que dos fuentes con la misma clave no choquen.
3. **Integraciones con fuentes de tareas (opcionales), en tres niveles:**
   - **Nivel 0, solo referencias.** No habla con ningún sistema. Funciona con cualquiera desde el primer día. El título y el estado, si se quieren, se escriben a mano.
   - **Nivel 1, lectura.** Resolver el título y el estado de un ticket y listar "mis tareas" (la base de `agenda` y de `list --mine`, [RFC 0005](../0005-vista-personal-agenda-y-backlog/README.md)).
   - **Nivel 2, escritura.** Publicar el tiempo como comentario, cambiar un estado, crear tickets (lo que hoy hace con Plane).

   La integración mínima útil es la de nivel 1: resolver una referencia y listar las tareas propias. No necesita comentarios ni adjuntos, lo que abarata mucho cada integración nueva.
4. **Perfiles.** Aislamiento físico: un directorio y una base por perfil.

### Perfiles

- **Aislamiento físico, no por columna.** `~/.cache/plane/profiles/<perfil>/` con su propia base. El perfil por defecto sigue siendo la ruta actual, para no romper ningún golden. Una tabla de metadatos guarda la huella `base_url|workspace` de la fuente; si no coincide con el entorno, se rechaza (cierra el defecto 0013).
- **Credenciales por perfil** en un archivo `0600` fuera del repositorio (`~/.config/plane-tracker/<perfil>.env`), **sin** fallback a `~/.zshrc.local` y sin valores por defecto de workspace.
- **Resolución del perfil:** variable `PLANE_PROFILE`; si no, un archivo marcador `.plane-profile` buscado hacia arriba desde el directorio de trabajo (como git); si nada aplica y hay varios perfiles, **error** (falla cerrado). Sin flag global, por el límite de la ayuda. Opcional y solo lectura: elegir el perfil por prefijo de ticket cuando las claves son disjuntas.
- **Baldes por perfil** (configuración, no listas fijas): un perfil de estudio necesita baldes de aprendizaje o de tesis, no los de ingeniería.
- **`focus` y sesiones:** `session_marks` vive en la base del perfil. Una sesión de agente que cruza perfiles se registra por tramos de tiempo; "lo ya registrado se resta" no vería el otro perfil, y habría que advertirlo.

### Métricas entre contextos

Solo en local, abriendo las bases de cada perfil en modo de solo lectura: minutos por perfil, proyecto y balde; número y mediana de sesiones y fragmentación; cambios de contexto por día; proporción medida frente a declarada; trabajo en curso y antigüedad. Nada personal sale hacia el trabajo, y el reporte que sube usa solo el perfil de trabajo. Tendencias y distribuciones, sin metas ni rachas (ley de Goodhart, ver P5).

### Pruebas de aislamiento (criterio de aceptación)

- Dos servidores falsos: con el perfil A activo, el servidor del perfil B no recibe ninguna petición, tampoco desde `outbox flush`.
- Un título único ("canario") de un perfil no aparece en ninguna petición ni en la cola de otro.
- Con varios perfiles y contexto ambiguo, cualquier escritura se rechaza.

## La decisión abierta: ¿dónde vive la verdad del tiempo?

La decisión hasta ahora (RFC 0011) es que **la fuente de verdad es Plane**: cada `comment add` publica un comentario con la telemetría en un bloque oculto y la base local se reconstruye desde ahí. La premisa nueva la pone en duda. **No está decidida**; quien usa la herramienta la considera una mezcla de ideas que hay que analizar a fondo.

| Opción | La verdad vive en | Resumen |
| :--- | :--- | :--- |
| **T1** | El sistema de tareas (como hoy) | El tiempo es un comentario del ticket; la base local es una caché reconstruible. |
| **T2** | Un libro local en SQLite | Cada perfil tiene su base como verdad; publicar en la fuente es opcional. |
| **T3** | Un libro local en archivos de texto | Markdown o JSONL legibles por una persona y por Obsidian; la base SQLite es una caché derivada. |
| **T4** | Libro local, más publicación opcional como metadata | Como T2 o T3, y además se publica un comentario en la fuente cuando esta lo admite, "por si algún día se lee". |

Criterios para decidir:

| Criterio | T1 tracker | T2 SQLite local | T3 archivos | T4 local y publicación opcional |
| :--- | :--- | :--- | :--- | :--- |
| Funciona con cualquier sistema de tareas (también sin ninguno) | **No**: exige comentarios que conserven el bloque oculto; sin verificar en Jira ni Linear, y no existe en archivos markdown | Sí | Sí | Sí |
| Una sola fuente de verdad | Sí | Sí (una máquina) | Sí | Sí si lo local manda y lo publicado es una copia |
| Varias máquinas | Sí, vía `report --refresh` | **No** sin sincronizar un archivo vivo (SQLite no tolera sincronizadores de archivos) | Sí, con un repositorio privado | Según T2 o T3 |
| Sobrevive a dejar un trabajo | **No**: el historial queda en el sistema de la organización | Sí | Sí | Sí |
| Legible sin la herramienta y con Obsidian | No | No | **Sí** | Según T2 o T3 |
| Privacidad de datos del trabajo | La organización ya los tiene | Local | **Riesgo** si el repositorio es personal (títulos de tickets de la organización) | Igual que T2 o T3 |
| Coste de implementación | Ninguno (existe) | Medio | Medio-alto | Medio |
| Reutiliza el código actual | Todo | El libro, sí; el transporte por comentarios pasa a opcional | Lo mismo, más una capa de archivos | Lo mismo |
| El reporte para quien supervisa | Igual | Igual | Igual | Igual |

Observaciones:

- **Dejar un trabajo.** Con T1 el historial de tiempo del propio trabajador vive en un sistema que no controla. Con un libro local conserva su historial, con la salvedad de que los títulos de tickets pueden ser información de la organización.
- **Trabajo y repositorio personal.** El libro del perfil de trabajo no debe sincronizarse con un repositorio personal sin pensarlo (T3). El libro de lo personal sí puede ir a un repositorio privado.
- **"Metadata por si algún día se lee"** apunta a T4: lo local manda y la publicación es opcional y por perfil.
- **Tendencia sin decidir:** T4 sobre T3 para lo personal y T4 sobre T2 para el trabajo (el libro no sale de la máquina de trabajo). Falta verificar que ese reparto sea razonable en uso real.

**Qué evidencia lo resolvería:** una o dos semanas con el libro local en uso real junto al Plane del trabajo, comprobando si el comentario publicado se echa de menos o nadie lo lee; y verificar si Linear y Jira conservan el bloque oculto en comentarios (hoy sin verificar).

## Escenarios

Los escenarios completos, con qué pasa hoy y qué haría falta en cada uno, están en [`escenarios.md`](./escenarios.md).

## Secuencia propuesta (no ejecutada)

Pasos que valen en **cualquier** premisa, y que ya estaban previstos:

1. Defectos [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) y [0003](../../defects/0003-standby-externo-sin-fuente-de-datos.md).
2. [Defecto 0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md) y **perfiles con aislamiento**, junto con el saneamiento de valores de organización del [0009](../../defects/0009-saneamiento-pendiente-de-datos-de-instancia.md).
3. [RFC 0005](../0005-vista-personal-agenda-y-backlog/README.md) fase 0: sus columnas nuevas se añaden de forma aditiva, y con una base por perfil no hay migración por contexto.

Pasos que dependen de la premisa nueva y de la decisión abierta:

4. **Decidir la verdad del tiempo** (ADR, tras el experimento descrito arriba). Reabre el RFC 0011.
5. **Libro de actividad independiente de los comentarios** (el worklog deja de depender del transporte de Plane) y **modo de solo referencias** (nivel 0).
6. **Baldes por perfil.**
7. **Integraciones de nivel 1** (resolver y listar), empezando por la que se vaya a usar de verdad.
8. **Integraciones de nivel 2** solo si hacen falta.

**Irreversible:** el formato de las claves e IDs de tickets y de las referencias calificadas, el nombre de la herramienta una vez publicada, y el primer layout de los directorios de perfil. **Barato:** elegir la integración mientras no exista la interfaz.

## Riesgos y qué no hacer ahora

- **Abstracción prematura.** No diseñar una interfaz de integración hasta tener dos fuentes reales; una interfaz con una sola sale mal.
- **Exceso de alcance y mantenedor único.** Cada integración es mantenimiento perpetuo de una API ajena; priorizar las que se usen.
- **Reescribir sin necesidad.** Es un rediseño, no un parche: hacerlo por etapas, con las pruebas golden como red de seguridad.
- **Privacidad.** Una fuga entre perfiles es el peor fallo; por eso el aislamiento va primero.
- **Métricas sobre uno mismo.** Convertirlas en meta las vuelve engañosas.
- **Publicar o renombrar.** El nombre actual y el repositorio público mezclan datos de instancia ([0009](../../defects/0009-saneamiento-pendiente-de-datos-de-instancia.md)); sanear primero y renombrar solo si se publica de verdad.

## Cuándo retomarlo

Cualquiera de estos hechos:

1. Se empieza a usar una **segunda instancia o un segundo sistema de tareas** (otro empleo, otro tracker, o lo personal en Plane).
2. Hay **tres días seguidos de registro personal real** y se echan de menos los estados o la vista semanal.
3. Se **deja un trabajo** y se quiere conservar el historial de tiempo.
4. Se decide **publicar la herramienta** como código abierto.
5. Ocurre el **primer incidente de contexto cruzado** (un registro en el sitio equivocado).

## Preguntas abiertas

Ya respondidas por quien usa la herramienta:

- Lo personal necesita **tiempo y también estados**, con varias áreas (idiomas, tesis, proyectos, cursos).
- La **administración personal** son tareas recurrentes sin cifras: se queda en su herramienta actual y entra en el libro como un ítem paraguas, sin migrar.
- Quien supervisa **prefiere un reporte resumido**; el tiempo publicado en el tracker es metadata opcional.
- **La verdad del tiempo no está decidida**; "quizá todo apunte a un libro local, pero habría que analizarlo".

Siguen abiertas:

1. ¿Se trabaja lo personal en más de una máquina? Decide entre archivos versionados en un repositorio privado y un servidor.
2. Si lo personal usa un Plane propio, ¿hay dónde alojarlo o se prefiere la nube, y se tolera mantenerlo?
3. ¿Esta herramienta se publicará como código abierto? Condiciona el nombre y el saneamiento del 0009.
4. ¿Pueden las claves de proyecto personales ser distintas de las del trabajo (para enrutar por prefijo)?
5. ¿Qué haría abandonar esto y volver a la herramienta anterior?
6. ¿Se acepta que el libro del perfil de trabajo no salga de la máquina de trabajo?

## Criterio de cierre

- Decisión registrada (ADR) sobre dónde vive la verdad del tiempo, con sus disparadores de revisión.
- Si se adopta la premisa nueva: perfiles con aislamiento, libro independiente del transporte de Plane, modo de solo referencias y las pruebas de aislamiento pasando.
- Los RFC 0011 y 0005 actualizados según esa decisión.
