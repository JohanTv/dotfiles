---
id: "0010"
title: El reporte no sincroniza con Plane los periodos que tienen registros locales parciales
status: abierto
created: 2026-10-31
summary: "`report` solo sincroniza si el periodo no tiene ningún registro local; con uno solo muestra un resultado parcial como completo y sin aviso."
---

# 0010 · El reporte no sincroniza con Plane los periodos con registros locales parciales

- **Área:** `report` (`scripts/plane_cli/cmd_report.py`), caché local de worklogs.
- **Relacionado:** RFC [0011](../rfcs/0011-cache-compartida-entre-maquinas/README.md) (caché entre máquinas) y la [cobertura de principios](../rfcs/0005-vista-personal-agenda-y-backlog/cobertura-actual-de-principios.md) (P5).

## Síntoma observado

Un reporte semanal mostró "Sin registros de actividad" de lunes a viernes y un total de unos pocos minutos. Tras ejecutar `report --week --refresh` el mismo reporte mostró varios días con actividad y un total de varias horas: los worklogs locales pasaron de 1 a 10. El primer resultado no avisaba de nada: se presentaba como completo.

## Causa verificada

`cmd_report` decide si sincronizar con esta condición (`cmd_report.py:134`):

```python
needs_sync = force_sync or (not has_entries and (now - last_synced > SYNC_COOLDOWN))
```

- `has_entries` es **global al periodo**: basta **un** registro local en toda la semana para que `report` no consulte Plane.
- La condición no compara contra Plane ni mira día por día, y tampoco muestra desde cuándo son los datos locales.
- La tabla `sync_metadata` guarda la marca `sync:<workspace>` solo después de una sincronización (`sync.py:159-162`); si nunca se sincronizó, `last_synced` vale 0 y la herramienta no lo dice.

## Por qué ocurre con más frecuencia entre máquinas

Los worklogs se **publican como comentarios** de Plane con su metadata oculta, y `report --refresh` los reconstruye de ahí. Eso hace de Plane la fuente de verdad, pero cada máquina tiene su propia caché: en una máquina que acaba de empezar a usarse, el primer `comment add` crea un registro local y a partir de ese momento el reporte de esa semana deja de sincronizar sola. Los registros publicados desde otra máquina no aparecen.

Lo que **no** se reconstruye desde Plane y vive solo en cada máquina: las marcas de foco (`session_marks`), la cola de salida de comentarios todavía sin publicar y las propuestas de duración pendientes (`last_proposal.json`).

## Comportamiento esperado

- Un reporte nunca presenta como completo un periodo que no se ha comparado con Plane.
- Si los datos locales no están al día, la primera línea del reporte lo dice y cómo corregirlo (`--refresh`).

## Nota tras la validación con la API real

La marca `sync:<workspace>` es global; la solución debe persistirla **por proyecto y periodo** (ver [0017](./0017-sincronizacion-de-worklogs-incompleta.md), cuyo diagnóstico se corrigió: `limit` no limita nada en la API). "Sincronizar por antigüedad independientemente de `has_entries`" solo es seguro si el sincronizador respeta el límite de tasa.

## Solución propuesta

1. **Aviso (mínimo):** al imprimir el reporte, mostrar "datos locales sincronizados hace X" o "nunca sincronizado; usa `--refresh`" cuando no haya una sincronización reciente del periodo.
2. **Criterio de sincronización:** sincronizar por antigüedad (`now - last_synced > SYNC_COOLDOWN`, 5 min) con independencia de `has_entries`, o por día sin registros locales; mantener `--offline`/`PLANE_OFFLINE` para no sincronizar.
3. **Degradación:** si Plane no responde, mantener el aviso actual ("Plane no responde") y añadir que el resultado es local y posiblemente incompleto.

## Criterio de cierre

- Con un periodo que tiene un único registro local y registros remotos de otros días, `report --week` los incluye sin necesidad de `--refresh`, o avisa explícitamente de que no están sincronizados.
- Golden tests de `report --week` con registros locales parciales, con y sin Plane disponible.
- La decisión de fondo sobre compartir la caché entre máquinas queda en el RFC 0011.
