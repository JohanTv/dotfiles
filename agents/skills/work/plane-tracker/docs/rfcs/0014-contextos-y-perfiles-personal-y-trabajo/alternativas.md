# Alternativas para el contexto personal y datos de apoyo

Parte del [RFC 0014](./README.md). Evaluación de una revisión independiente de solo lectura (código del repositorio y documentación pública). Las APIs cambian: los datos de abajo son de 2026-11-01 y lo marcado "no verificado" no se pudo comprobar.

## Acoplamiento real con Plane

| Agnóstico (sin red) | Acoplado a Plane |
| :--- | :--- |
| `worklog.py`, `timeutil.py`, `proposals.py`, `proposal_store.py`, `mdhtml.py`, `scripts/session_clock.py`, `scripts/flow_metrics.py` | `api`, `circuit`, `resolve`, `cache`, `sync`, `outbox`, `outbox_flush`, `create_guard`, `attachments` y todos los `cmd_*` |

`flow.py` es mixto: calcula, pero lee `/activities/` de Plane. No hay una capa a la que enchufar otro backend: las rutas `/api/v1/workspaces/{ws}/projects/...` se construyen a mano en unos quince módulos.

**Operaciones mínimas que necesitaría una interfaz de backend (unas doce):** listar proyectos y resolver `clave-N`; listar, obtener, crear y actualizar tickets (estado, etiquetas, prioridad, título, descripción); listar estados y etiquetas; listar, crear (idempotente), editar y borrar comentarios; transiciones de estado; usuario actual y sonda de disponibilidad; opcionalmente enlaces y adjuntos.

**Costura real:** serían dos piezas, un `TrackerBackend` (tickets) y un `WorklogStore` (hoy implementado como comentarios del ticket).

**Regresión:** las pruebas golden comparan las peticiones HTTP que recibe el servidor falso; si un refactor conserva las peticiones byte a byte, esas pruebas son la red de seguridad. Un backend que no pase por HTTP necesitaría una suite nueva. Esfuerzos estimados (opinión): interfaz más backend local, de 3 a 6 semanas de un único mantenedor; perfil por directorio con la ruta por defecto intacta, de 2 a 4 días y sin romper ningún golden.

## ¿Se puede hoy sin código?

Casi, con riesgos. Un segundo Plane y un `HOME` aparte (la caché es `~/.cache/plane` y solo `HOME` la mueve). Cambiar `HOME` rompe la medición de sesiones de agente, que lee transcripts relativos a `HOME`: haría falta enlazar esos directorios (inferencia, no probada). Sirve para validar, no para uso continuo. Ver el [defecto 0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md) para la fuga de la cola de salida, que ocurre con cualquier configuración de una sola base.

## Opciones para el contexto personal

| | Opción | Encaje | Estados | Telemetría oculta | Privacidad | Esfuerzo | Bloqueo | Valor OSS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| A | Backend local propio | Bueno en finanzas, regular en el resto | Propios; reutilizar los 5 grupos de Plane | No hace falta: el worklog es nativo | La mejor | Alto: reimplementar IDs, búsqueda, comentarios | Ninguno | Medio: es otro producto, y contradice "la caché es desechable" del RFC 0011 |
| B | Segundo Plane (autoalojado o nube) como otro perfil | Excelente: workspace más proyectos es su modelo | Idénticos | Sí, mecanismo ya probado | Autoalojado: alta. Nube: terceros | Bajo | Bajo | Alto |
| C | Adaptador Linear | Bueno para proyectos | `triage`, `backlog`, `unstarted`, `started`, `completed`, `canceled`, `duplicate`; mapea casi 1:1 | Se conserva en descripciones según fuentes de terceros; **en comentarios, no verificado** | SaaS | Alto (GraphQL) | SaaS | Medio |
| D | Adaptador Todoist | Bueno para bandeja de entrada y cursos | **No hay estados**: abierto o completado, con secciones y subtareas | **No**: los comentarios no admiten HTML | SaaS | Alto y con pérdida | SaaS | Bajo |
| E | Adaptador GitHub Issues/Projects | Solo proyectos propios y de código abierto | Abierto o cerrado, más un campo `Status` de proyecto | Se conserva en el cuerpo en bruto de la API (fuente de segunda mano) | SaaS; público si el repositorio lo es | Alto | SaaS | Medio |
| F | No unificar: Todoist para tareas y la herramienta solo registra tiempo | Cubre tareas, no estados | Sin estados | Hace falta un libro local aparte, que es una versión pequeña de A | Igual que hoy | Medio | Todoist | Bajo |
| G | Archivos de texto (markdown, todo.txt) con la caché SQLite desechable | Bueno en finanzas y tesis | Un campo de estado | Trivial, sin bloque oculto | Alta | Medio-alto | Ninguno | Medio-alto |

**Conclusión de la revisión:** la opción B con perfiles ahora. Si en uso real el servidor estorba, la segunda alternativa es G, no A (G respeta la fuente única de verdad: la verdad vive en archivos y se sincroniza con un repositorio privado). F no cumple lo que se pidió, estados en lo personal.

## Datos de las APIs (vigentes a 2026-11-01; "N.V." = no verificado)

- **Plane:** `/api/v1/`, cabecera `X-API-Key`, 60 solicitudes por minuto; admite también OAuth. https://developers.plane.so/api-reference/introduction y https://developers.plane.so/api-reference/state/overview (cinco grupos de estado).
- **Linear:** 2.500 solicitudes por hora con clave de API, 5.000 con OAuth, y 10.000 puntos de complejidad por consulta. https://linear.app/developers/rate-limiting. Tipos de estado según una fuente de segunda mano: https://docs.rs/linear-api/0.1.0/linear_api/enum.WorkflowStateType.html.
- **Todoist:** la API REST v2 devuelve 410 y se migró a la API v1 unificada en `api.todoist.com/api/v1` (fuente de segunda mano: https://forums.getdrafts.com/t/todoist-api-updates-deadline-febrary-2026/16403). Límite de unas 1.000 solicitudes cada 15 minutos (N.V.). Sin HTML en comentarios: https://www.todoist.com/help/articles/format-text-in-a-todoist-task-e5dHw9. La documentación oficial no se pudo consultar. Prioridad invertida respecto a Plane, de memoria (N.V.).
- **GitHub:** 5.000 solicitudes por hora (de memoria, N.V.); la API REST de Projects v2 no se verificó.

## Lo que no se pudo verificar

- Que Linear conserve el bloque oculto en comentarios (solo hay evidencia en descripciones).
- La documentación oficial de Todoist y la API de Projects v2 de GitHub.
- Los límites de los planes gratuitos y los requisitos para autoalojar Plane; la versión vigente de Plane CE (`SKILL.md` cita la v1.2.3).
- El comportamiento de un `HOME` aparte con enlaces simbólicos.
- Las estimaciones de esfuerzo son opinión.
