# Índice de documentos de desarrollo

> Generado por `scripts/docs_index.py`; no se edita a mano. Un RFC solo existe en el código si su estado es
> `implementado`; un defecto solo está resuelto si su estado es `corregido`. Convenciones: [README](./README.md).


## Defectos

| ID | Título | Estado | Resumen |
| :--- | :--- | :--- | :--- |
| 0001 | [No se puede fijar inicio y fin reales al registrar tiempo declarado](defects/0001-registro-retroactivo-de-horas.md) | abierto | `comment add --duration` usa la hora de publicación como fin; el registro retroactivo distorsiona la fusión de intervalos. |
| 0003 | [El "Standby externo" del reporte no tiene fuente de datos](defects/0003-standby-externo-sin-fuente-de-datos.md) | abierto | El reporte afirma "Sin bloqueos reportados" aunque ningún flujo puede reportar bloqueos; la decisión de producto está en 0006. |
| 0004 | [Verificar que Plane devuelve `external_id` en los GET de comentarios](defects/0004-verificar-external-id-en-comentarios.md) | abierto | La cola de salida asume un contrato de `external_id` de Plane que no se ha confirmado en una instancia real. |
| 0009 | [Saneamiento pendiente de datos de instancia y de personas en el repositorio](defects/0009-saneamiento-pendiente-de-datos-de-instancia.md) | abierto | El historial publicado ya se reescribió; quedan valores por defecto en el código, claves de proyecto como ejemplos y la purga de copias fuera del repositorio. |
| 0010 | [El reporte no sincroniza con Plane los periodos que tienen registros locales parciales](defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md) | abierto | `report` solo sincroniza si el periodo no tiene ningún registro local; con uno solo muestra un resultado parcial como completo y sin aviso. |
| 0013 | [La cola de salida no registra a qué instancia pertenece cada comentario](defects/0013-cola-de-salida-sin-instancia-de-destino.md) | abierto | `outbox flush` publica con las credenciales del entorno actual; con dos instancias y una sola base local, un comentario podría publicarse en la instancia equivocada. |

## RFC

| ID | Título | Estado | Resumen |
| :--- | :--- | :--- | :--- |
| 0002 | [Gestión de worktrees multi-repo por ticket](rfcs/0002-worktrees-multi-repo-por-ticket.md) | propuesto | Script independiente que crea, por ticket, un worktree en cada repo implicado con rama y base verificadas; sin implementar. |
| 0005 | [Vista personal de actividades (agenda) y registro de diferimiento del backlog](rfcs/0005-vista-personal-agenda-y-backlog/README.md) | borrador | `list --mine`, panel `agenda` con carga, vencidos y backlog propio, y registro del motivo por el que se difiere algo importante. |
| 0006 | [Decidir la fuente de datos del "Standby externo"](rfcs/0006-standby-externo-fuente-de-datos.md) | borrador | Quitar la línea de bloqueos del reporte o alimentarla (flag, o tiempo en Pausado desde las transiciones). |
| 0011 | [Caché de la herramienta entre varias máquinas (¿base de datos compartida?)](rfcs/0011-cache-compartida-entre-maquinas/README.md) | borrador | Decidir cómo trabajar desde varias máquinas con la misma instancia de Plane; la recomendación actual es no añadir una base de datos remota y arreglar la sincronización. |
| 0014 | [Contextos, perfiles y fuentes de tareas intercambiables](rfcs/0014-contextos-y-perfiles-personal-y-trabajo/README.md) | borrador | Aplazado a propósito. Usar la herramienta en varios contextos (trabajos, personal) y con varios sistemas de tareas; la decisión abierta es dónde vive la verdad del tiempo. |

## Decisiones

| ID | Título | Estado | Resumen |
| :--- | :--- | :--- | :--- |
| 0007 | [Los documentos del repositorio son agnósticos de instancia, empresa y personas](decisions/0007-documentos-agnosticos-de-instancia.md) | aceptado | Ningún documento del repo contiene hosts, IPs, nombres de personas o clientes ni datos de horas reales; la evidencia concreta vive fuera del repo. |
| 0008 | [Documentos de desarrollo en docs/ por tipo, con ID global y estado en la cabecera](decisions/0008-estructura-de-docs-por-tipo-con-id-global/README.md) | aceptado | `docs/defects`, `docs/rfcs` y `docs/decisions`; ID `NNNN` único; estado en el front-matter; índice generado. |
| 0012 | [Estrategia de pruebas rápidas - paralelo por procesos, servidor falso ágil y lanzador sin esperas](decisions/0012-estrategia-de-pruebas-rapidas/README.md) | aceptado | La suite pasó de 157 s a 97 s en secuencial y a 33-48 s en paralelo, sin tocar el código de producción ni añadir dependencias. |
| 0015 | [Reloj central en producción y reloj congelado en las pruebas](decisions/0015-reloj-central-y-reloj-congelado-en-las-pruebas.md) | aceptado | Toda lectura de la hora pasa por un único módulo y las pruebas golden congelan la hora desde un lanzador, sin variable de entorno en producción. |
