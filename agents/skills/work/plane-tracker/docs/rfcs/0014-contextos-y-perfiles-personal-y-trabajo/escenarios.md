# Escenarios de uso

Parte del [RFC 0014](./README.md). Cada escenario indica qué pasa **hoy** con la herramienta (un solo entorno forzado), qué haría falta, y qué nivel de integración y de perfil usa. Los niveles de integración son: **0** solo referencias, **1** lectura (resolver y listar), **2** escritura (publicar tiempo, cambiar estado, crear tickets).

Lo que se afirma de Jira, Linear y Todoist es de memoria o de segunda mano y no está verificado salvo donde se indique (ver `alternativas.md`).

## Resumen

| # | Escenario | Hoy | Perfiles | Integración mínima |
| :--- | :--- | :--- | :--- | :--- |
| S1 | Un solo trabajo con Plane | Funciona | 1 (el de siempre) | 2 (Plane) |
| S2 | Trabajo con Plane y personal con otro Plane propio | Se mezclan datos; riesgo de fuga | 2 | 2 (Plane) en ambos |
| S3 | Dos trabajos, ambos con Plane | Se mezclan datos; riesgo de fuga | 2 | 2 (Plane) en ambos |
| S4 | Trabajo con Plane y otro con Linear | No funciona con Linear | 2 | 2 (Plane) y 0 o 1 (Linear) |
| S5 | Un trabajo con Jira | No funciona | 1 o más | 0 al inicio |
| S6 | Se propone la herramienta en un trabajo nuevo con otro sistema | No funciona | 1 más | 0 o 1 |
| S7 | El sistema de tareas propio son archivos markdown (Obsidian) | No funciona | 1 | 1 o 2 (markdown) |
| S8 | Lo personal sigue en una herramienta de tareas personal | No integrado | 1 | 0 |
| S9 | Registrar tiempo por tema sin tareas (por ejemplo, idiomas) | No integrado | 1 | 0 |
| S10 | Un mismo contexto en dos máquinas | La caché es por máquina | 1 por máquina | según la verdad del tiempo |
| S11 | Dos contextos el mismo día en la misma máquina | Un solo contexto posible | 2 | por perfil |
| S12 | Se deja un trabajo | El historial queda en el sistema de la organización | 1 | n/a |
| S13 | Varias personas usan la herramienta | Una sola persona asumida | 1 por persona | por persona |
| S14 | Un agente de IA trabaja en un directorio ambiguo | Usa el entorno que haya | n | n/a |
| S15 | La fuente de tareas no responde | Funciona sin conexión para lo local | cualquiera | cualquiera |
| S16 | La organización migra de un sistema de tareas a otro | No contemplado | 1 | 0 mientras tanto |
| S17 | Dos fuentes con la misma clave de ticket | Se pisan | 2 | n/a |

## S1 · Un solo trabajo con Plane (el caso de hoy)

- **Hoy:** funciona. La herramienta está pensada para esto.
- **Con el rediseño:** nada cambia para quien lo use así; el perfil por defecto es la ruta actual.
- **Riesgo:** ninguno nuevo. Hay que mantener intactas las pruebas golden.

## S2 · Trabajo con Plane y personal con un Plane propio

- **Hoy:** la caché es única (`~/.cache/plane`), `projects` se pisa por clave de proyecto y `worklogs` no distingue instancia. La cola de salida publica con las credenciales del entorno activo. **Un comentario personal puede publicarse en la instancia del trabajo** si existe el mismo prefijo de ticket ([0013](../../defects/0013-cola-de-salida-sin-instancia-de-destino.md)).
- **Hace falta:** perfiles con aislamiento físico y huella de instancia en la cola. No hace falta ningún adaptador.
- **Opción de bajo coste hoy:** un `HOME` aparte con enlaces a los transcripts de agentes (inferencia no probada). Sirve para validar, no para uso continuo.

## S3 · Dos trabajos, ambos con Plane

- **Hoy:** el mismo problema que S2. Además, las listas de claves de proyecto y el workspace por defecto están fijados en el código ([0009](../../defects/0009-saneamiento-pendiente-de-datos-de-instancia.md)).
- **Hace falta:** perfiles y credenciales por perfil; quitar los valores fijos. Un perfil por empleo, cada uno con su base.
- **Cuidado:** los reportes que cada organización recibe deben salir solo de su perfil.

## S4 · Un trabajo con Plane y otro con Linear

- **Hoy:** no funciona con Linear; todo habla con la API de Plane.
- **Hace falta:** perfiles, y una de dos: **nivel 0** (solo referencias; el tiempo se registra en local con la clave de Linear como etiqueta, sin consultar nada) o una integración de Linear de nivel 1 o 2.
- **Por verificar:** si Linear conserva el bloque oculto de telemetría en comentarios (solo hay evidencia en descripciones) y los mapeos de estados (los tipos de Linear se parecen a los grupos de Plane, con `triage` y `duplicate` de más).

## S5 · Un trabajo con Jira

- **Hoy:** no funciona.
- **Hace falta:** igual que S4. Empezar en **nivel 0**, que no depende de la API de Jira.
- **Por verificar:** si Jira Cloud conserva un bloque oculto dentro de un comentario (creo que usa un formato propio para los comentarios, no verificado) y cómo se mapean sus estados y prioridades.
- **Observación:** Jira suele ser un sistema que la persona no elige; conviene que el nivel 0 sea una opción de primera clase y no un parche.

## S6 · Se propone la herramienta en un trabajo nuevo

Dos variantes:

- **La herramienta como sistema de tareas propio:** exigiría que la herramienta gestione tickets, y eso es lo que **no** se quiere (premisa nueva). Se desaconseja.
- **La herramienta como registro de tiempo sobre el sistema que ya usen** (Linear, Plane, Jira...): nivel 0 desde el primer día, y una integración de nivel 1 si hay interés. Si el equipo no tiene sistema y se propone uno, puede ser Plane (ya está soportado) o el que prefieran, sin que la herramienta dependa de él.

## S7 · El sistema de tareas son archivos markdown (Obsidian)

- **Hoy:** no funciona.
- **Hace falta:** una integración de markdown: cada tarea es una nota o una línea con estado en el front-matter o en una casilla. Nivel 1 (leer tareas y estados) y, si se quiere, nivel 2 (cambiar un estado escribiendo el archivo).
- **Ventaja:** sin red, sin cuentas y legible por una persona; Dataview o el plugin de tablas dan filtros y vistas sin código.
- **Cuidado:** si las tareas del trabajo y las personales conviven en la misma bóveda, hay que respetar el aislamiento (un perfil por bóveda o por carpeta).

## S8 · Lo personal sigue en una herramienta de tareas personal

(Ejemplo: tareas recurrentes de administración personal, como pagar tarjetas o cancelar suscripciones.)

- **Hoy:** no integrado; no hace falta.
- **Hace falta:** nada, o **nivel 0**: un ítem paraguas en el libro ("administración personal") para registrar tiempo si se quiere, sin migrar las tareas. Aplica la regla de menos de 15 minutos: no se crean tickets para tareas cortas.
- **No conviene** usarla como fuente de verdad del tiempo: no tiene estados intermedios y, según la documentación, sus comentarios no admiten HTML, así que el bloque oculto no sobreviviría.

## S9 · Registrar tiempo por tema, sin tareas

(Ejemplo: media hora de idiomas.)

- **Hoy:** el worklog exige un ticket.
- **Hace falta:** nivel 0 con una referencia de tema (un ítem paraguas por tema: idiomas, tesis, cursos) y baldes propios del perfil (aprendizaje, investigación).
- **Es el caso que más pesa a favor de un libro local:** no hay sistema de tareas con el que hablar.

## S10 · Un mismo contexto en dos máquinas

(Ejemplo: lo personal en un portátil de trabajo y uno personal; o el trabajo en dos equipos.)

- **Hoy:** cada máquina tiene su caché. El worklog publicado en el ticket se recupera con `report --refresh`, pero la cola sin publicar, las marcas de foco y las propuestas pendientes viven solo en esa máquina ([0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md), [RFC 0011](../0011-cache-compartida-entre-maquinas/README.md)).
- **Depende de la verdad del tiempo:**
  - Verdad en el tracker (T1): se sigue con `--refresh`.
  - Libro local en SQLite (T2): no se puede sincronizar sin riesgo de corrupción.
  - Libro en archivos (T3): sincronizable con un repositorio privado.
- **Cuidado con el trabajo:** el libro de un perfil de trabajo no debe viajar a un espacio personal.

## S11 · Dos contextos el mismo día en la misma máquina

- **Hoy:** imposible sin mezclar datos.
- **Hace falta:** resolución del perfil por directorio (archivo marcador `.plane-profile`) o por variable, con **falla cerrado** si es ambiguo.
- **Cuidado con las sesiones de agente:** una sesión puede cruzar perfiles; se registra por tramos de tiempo, y "lo ya registrado se resta" no vería el otro perfil.
- **Reportes:** un resumen entre contextos solo en local, nunca enviado.

## S12 · Se deja un trabajo

- **Hoy:** el historial de tiempo vive en el sistema de la organización (comentarios con metadata) y la caché local lo reconstruye; al perder el acceso, se pierde esa fuente.
- **Con un libro local (T2, T3 o T4):** se conserva el historial propio.
- **Cuidado:** los títulos de tickets pueden ser información de la organización; conviene poder exportar el libro **sin títulos** (solo claves, tiempos y baldes), o conservar solo agregados.

## S13 · Varias personas usan la herramienta

(Un equipo, o usuarios de la versión de código abierto.)

- **Hoy:** una sola persona asumida, con valores de una organización fijados en el código.
- **Hace falta:** quitar esos valores (0009) y que todo salga de la configuración de cada perfil. Cada persona tiene su propia base; no hay una base compartida.
- **Vista de equipo:** si hiciera falta (agenda de equipo), se construiría leyendo la fuente de tareas, no compartiendo bases. Es uno de los disparadores del RFC 0011.

## S14 · Un agente de IA trabaja en un directorio ambiguo

- **Hoy:** usa el entorno que haya; `SKILL.md` está redactado para una organización concreta, así que un agente en un directorio personal podría publicar en la organización.
- **Hace falta:** **fallar cerrado**: con varios perfiles y sin contexto resoluble, rechazar cualquier escritura y preguntar. `SKILL.md` debe decir qué perfil usar y cómo se resuelve.

## S15 · La fuente de tareas no responde

- **Hoy:** las lecturas responden con lo local y avisan su antigüedad; `comment add` guarda y encola; el resto falla con código 3.
- **Con el rediseño:** el libro es local, así que registrar tiempo nunca depende de la red. La cola de salida pasa a ser parte de una integración de nivel 2, con su huella de instancia.

## S16 · La organización migra de un sistema de tareas a otro

(Ejemplo: de Plane a Jira.)

- **Hoy:** no contemplado; las claves cambian y los comentarios publicados se quedan en el sistema antiguo.
- **Hace falta:** referencias estables. El libro conserva las claves antiguas y se añade un alias o una nueva fuente al perfil; el nivel 0 sigue funcionando durante la transición.

## S17 · Dos fuentes con la misma clave de ticket

(Ejemplo: dos empleos con un proyecto `PROJ`.)

- **Hoy:** `projects` tiene como clave la clave de proyecto, así que se pisan; el worklog no distingue.
- **Hace falta:** la referencia se califica con el perfil (`perfil:CLAVE-N`) y el aislamiento físico impide que se mezclen. El enrutamiento automático por prefijo solo sirve cuando las claves son disjuntas.

## Combinaciones frecuentes

- **Lo mínimo útil:** perfiles con aislamiento (S2, S3, S11, S14, S17) más el modo de solo referencias (S4, S5, S6, S9). Cubre casi todo sin escribir ni una integración.
- **Lo que exige un adaptador:** listar "mis tareas" y ver estados en un sistema que no sea Plane (S4, S5, S7). Se construye cuando se use de verdad, empezando por una sola.
- **Lo que depende de la decisión abierta:** S10, S12 y parte de S15 (dónde vive la verdad del tiempo).
