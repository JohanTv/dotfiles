---
id: "0011"
title: Caché de la herramienta entre varias máquinas (¿base de datos compartida?)
status: borrador
created: 2026-10-31
summary: Decidir cómo trabajar desde varias máquinas con la misma instancia de Plane; la recomendación actual es no añadir una base de datos remota y arreglar la sincronización.
---

# 0011 · Caché de la herramienta entre varias máquinas

- **Área:** caché local (`~/.cache/plane/worklogs.db`), `report`, `outbox`, `focus`.
- **Defecto relacionado:** [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md).
- **Principios:** [`principles.md`](../../principles.md) (P2 autonomía, una sola fuente de verdad, local-first).
- **Alternativas evaluadas:** [`alternativas.md`](./alternativas.md).

> **Nota (2026-11-01):** este RFC parte de que la fuente de verdad es Plane. El [RFC 0014](../0014-contextos-y-perfiles-personal-y-trabajo/README.md) pone esa premisa en duda (un libro local podría ser la verdad del tiempo, con Plane como integración opcional). Aceptar la recomendación de aquí como comportamiento a corto plazo es compatible con ambas, pero la decisión de fondo depende de la del 0014 y podría quedar reemplazada.

## Pregunta

Una persona trabaja desde más de una máquina (por ejemplo, la del trabajo y una personal) contra la misma instancia de Plane. ¿La caché debe compartirse, por ejemplo en una base de datos remota (Supabase u otra), o basta con la caché local de cada máquina?

## Cómo funciona hoy

- La **fuente de verdad es Plane**. Cada `comment add` publica un comentario con su telemetría en un bloque oculto, y la caché local de worklogs se puede **reconstruir** desde esos comentarios con `report --refresh` (verificado: una sincronización forzada reconstruyó los registros de otros días).
- La caché de cada máquina es **desechable**, salvo tres cosas que solo existen en esa máquina: las marcas de foco (`session_marks`), la cola de salida con comentarios aún sin publicar (`outbox`) y las propuestas de duración pendientes (`last_proposal.json`, efímeras, 30 min).
- La sincronización con Plane no es automática en general: solo ocurre con `--refresh`, o cuando el periodo consultado no tiene ningún registro local y pasaron más de 5 minutos desde la última (defecto 0010).

## Por qué el problema observado no exige una base de datos compartida

El síntoma (un reporte semanal que omitía casi todo el tiempo) se debió a la condición de sincronización de `report`, no a que faltara un almacén común: los datos estaban en Plane y la sincronización forzada los recuperó. Es un defecto de la herramienta (0010), no una carencia de arquitectura.

## Recomendación (borrador)

1. **Ahora:** corregir el defecto 0010 (aviso de desfase y sincronización por antigüedad). Es barato y resuelve el caso observado.
2. **Procedimiento al cambiar de máquina:** publicar la cola pendiente antes de dejar una máquina (`plane-tracker outbox flush`) y sincronizar en la nueva (`report --refresh`). Documentarlo en la guía operativa.
3. **No añadir una base de datos remota todavía.** Introduce una segunda fuente de verdad, envía datos de trabajo a un tercero (P2), exige red (rompe local-first) y obliga a cada persona que use la herramienta a montar infraestructura propia.
4. **Disparadores para reabrir la decisión** (cualquiera, medido): (a) hace falta compartir en tiempo real estado que no está en Plane (cola, foco); (b) varias personas necesitan una vista derivada común que Plane no ofrece; (c) la sincronización de un periodo típico supera un tiempo inaceptable con la API real.

## Criterio de cierre

- Decisión registrada como ADR (aceptar la recomendación o adoptar otra alternativa con sus disparadores).
- Si se acepta: el defecto 0010 corregido y el procedimiento de cambio de máquina documentado.
