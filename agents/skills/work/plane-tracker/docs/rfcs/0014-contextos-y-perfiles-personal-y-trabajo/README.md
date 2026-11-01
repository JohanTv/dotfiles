---
id: "0014"
title: Contextos y perfiles - usar la herramienta para trabajo y para lo personal
status: borrador
created: 2026-11-01
summary: Perfil como aislamiento físico (un directorio y una base por perfil), un segundo Plane para lo personal y sin interfaz de backend hasta que el uso real la justifique.
---

# 0014 · Contextos y perfiles: trabajo y vida personal con la misma herramienta

- **Alternativas evaluadas y datos de las APIs:** [`alternativas.md`](./alternativas.md).
- **Defecto relacionado:** [0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md) (la cola de salida no registra su instancia de destino).
- **Principios:** [`principles.md`](../../principles.md) (P2 autonomía, local-first, una sola fuente de verdad).

## Necesidad

Una misma persona quiere usar la herramienta en dos mundos, a veces el mismo día y en la misma máquina:

- **Trabajo:** una instancia de Plane de la organización, con varios proyectos.
- **Personal:** áreas como idiomas, tesis, proyectos propios (incluida esta herramienta), finanzas y cursos. Se quieren **tickets con estados**, no solo tiempo, y cada área se ve como un proyecto dentro de un contexto, igual que workspace y proyectos en Plane.
- **Métricas de la semana** que crucen ambos contextos.

## Restricciones

- Lo personal **nunca** puede llegar a la instancia de la organización (P2). La cola de salida publica comentarios, así que un error de contexto es una fuga.
- Privacidad: el repositorio es público y los documentos son agnósticos ([0007](../../decisions/0007-documentos-agnosticos-de-instancia.md)); las finanzas son sensibles.
- Local-first, solo biblioteca estándar, mantenedor único, árbol de comandos raíz cerrado y ayuda global sin margen (`tests/test_cli_tree.py`).

## Hallazgos que condicionan el diseño (verificados en el código)

- **No existe una costura de backend.** Las rutas `/api/v1/workspaces/...` se construyen a mano en unos 15 módulos. Los módulos agnósticos (sin red) son `worklog`, `timeutil`, `proposals`, `proposal_store`, `mdhtml`, `session_clock` y `flow_metrics`; el resto habla con Plane. Detalle en `alternativas.md`.
- **El worklog viaja por el transporte de Plane:** se guarda como bloque oculto en un comentario del ticket y se reconstruye desde ahí. Otro backend exigiría que conserve ese bloque, o un almacén de worklogs aparte.
- **La base local no distingue instancias:** `projects` tiene como clave la clave de proyecto (dos instancias con la misma clave se pisan), `worklogs` no tiene workspace ni proyecto en su clave primaria, y unas 42 de 43 consultas a las tablas locales no filtran por workspace. Añadir una columna de contexto obligaría a tocarlas todas, y olvidar una sería una fuga silenciosa.
- **Valores de una organización concreta en el código**, más de los que lista el [0009](../../defects/0009-saneamiento-pendiente-de-datos-de-instancia.md): listas fijas de claves de proyecto en `sync.py` y `cmd_read.py`, y un workspace y un proyecto por defecto en `cli.py`.
- **La caché no se puede reubicar por variable** (`config.py`), y la medición de sesiones de agente lee transcripts relativos a `HOME`.

## Recomendación (borrador)

1. **Perfil como aislamiento físico, no por columna.** Un directorio y una base por perfil (`~/.cache/plane/profiles/<perfil>/`). El perfil por defecto sigue siendo la ruta actual, para no romper ningún golden. Una tabla de metadatos guarda la huella `base_url|workspace`; si no coincide con el entorno, se rechaza (esto además cierra el defecto 0013 en las instalaciones actuales).
2. **Credenciales por perfil**, en un archivo `0600` fuera del repositorio (`~/.config/plane-tracker/<perfil>.env`), **sin** fallback a `~/.zshrc.local` ni valores por defecto de workspace.
3. **Resolución del perfil:** variable `PLANE_PROFILE`; si no, un archivo marcador `.plane-profile` buscado hacia arriba desde el directorio de trabajo (como git); si nada aplica y hay varios perfiles, **error** (falla cerrado). Sin flag global, por el límite de la ayuda.
4. **Un segundo Plane para lo personal**, que ya es el modelo de la herramienta (workspace y proyectos, los mismos cinco grupos de estado, telemetría ya probada). No requiere adaptador.
5. **Aplazar el backend local y la interfaz de backend.** Una interfaz diseñada con un solo backend real sale mal; se extrae cuando exista el segundo. Un backend local obliga a reimplementar un tracker (identificadores, búsqueda, comentarios), con un coste estimado de semanas. Si en uso real un servidor estorba, la alternativa es el almacenamiento en archivos de texto, no un tracker propio.
6. **Baldes por perfil** (configuración en lugar de listas fijas): un perfil de estudio necesita baldes de aprendizaje o de tesis, no los de ingeniería.
7. **Métricas entre contextos** solo en local, abriendo las bases de cada perfil en modo de solo lectura: minutos por perfil, proyecto y balde; sesiones y fragmentación; cambios de contexto por día; trabajo en curso y antigüedad. Nada personal sale hacia el trabajo, y el reporte que sube usa solo el perfil de trabajo. Tendencias y distribuciones, sin metas ni rachas (ley de Goodhart).

## Finanzas

Lo sensible son las cifras, las cuentas y los identificadores, más que el título de una tarea. Regla propuesta: **referencias, no datos** (nada de montos, cuentas ni documentos en títulos ni comentarios). Donde viva: un proyecto del Plane personal si es autoalojado, o un perfil solo local si se quiere ser estricto. La biblioteca estándar no cifra SQLite; el cifrado sería de disco o del archivo.

## Secuencia propuesta

1. Defectos [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) y [0003](../../defects/0003-standby-externo-sin-fuente-de-datos.md).
2. Decisión (ADR) sobre el [RFC 0011](../0011-cache-compartida-entre-maquinas/README.md), añadiendo que un perfil implica una base por perfil.
3. Defecto 0013 y perfiles con aislamiento, junto con el saneamiento de valores de organización del 0009.
4. [RFC 0005](../0005-vista-personal-agenda-y-backlog/README.md) fase 0: sus columnas nuevas se añaden de forma aditiva, y con una base por perfil no hay migración por contexto.
5. Baldes por perfil.

**Irreversible:** el formato de claves e IDs de tickets, el nombre de la herramienta una vez publicada y el primer layout de directorios de perfil. **Barato:** elegir el backend mientras no exista la interfaz.

## Pruebas de aislamiento (criterio de aceptación)

- Dos servidores falsos: con el perfil A activo, el servidor del perfil B no recibe ninguna petición, tampoco desde `outbox flush`.
- Un título único ("canario") de un perfil no aparece en ninguna petición ni en la cola del otro.
- Con varios perfiles y contexto ambiguo, cualquier escritura se rechaza.

## Paso mínimo de validación (1-2 semanas, sin construir adaptadores)

Un segundo Plane para lo personal y una caché aparte (un `HOME` distinto, con enlaces simbólicos a los transcripts de agentes para que la medición de sesiones siga funcionando; esto último es una inferencia no probada). Usarlo para idiomas, tesis y finanzas y mirar el reporte semanal por separado.

**Criterios de abandono:** se pierden datos o hay una fuga entre perfiles; operar el servidor cuesta más de una hora por semana; se dejan de registrar tareas (más de tres días sin tocarlas); se vuelve a la herramienta anterior por costumbre.

## Preguntas abiertas

1. ¿Se trabaja lo personal en más de una máquina? Decide entre un servidor y archivos versionados en un repositorio privado: un libro solo local no sirve en ese caso.
2. ¿Hay dónde alojar un Plane (servidor propio) o se prefiere el servicio en la nube, y se tolera mantenerlo?
3. ¿Se quiere medir tiempo en lo personal, o solo estados y una vista semanal?
4. ¿Qué es lo sensible de las finanzas: los títulos, o las cifras y cuentas?
5. ¿Esta herramienta se publicará como código abierto? Condiciona el nombre y el saneamiento del 0009.
6. ¿Pueden las claves de proyecto personales ser distintas de las del trabajo (para enrutar por prefijo)?
7. ¿Qué haría abandonar esto y volver a la herramienta anterior?

## Criterio de cierre

Decisión registrada (ADR) con la arquitectura elegida y sus disparadores de revisión; si se acepta, defecto 0013 corregido y las pruebas de aislamiento pasando.
