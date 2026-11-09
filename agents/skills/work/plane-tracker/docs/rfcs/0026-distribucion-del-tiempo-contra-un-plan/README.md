---
id: "0026"
title: Medir la distribución del tiempo contra un plan declarado por la persona
status: borrador
created: 2026-11-03
summary: El reporte de tiempo no compara lo registrado con ningún plan de distribución; se propone clasificar el trabajo en clases (feature, soporte, deuda, aprendizaje, overhead), derivarlas del ticket, comparar sobre tiempo de ingeniería y decir siempre cuánto no se registró.
---

# 0026 · Medir la distribución del tiempo contra un plan declarado por la persona

- **Área:** `report time` (consola y JSON), `comment add` / `comment edit` (flag nuevo), caché `worklogs`, bloque oculto de telemetría, configuración local.
- **Principios:** [P1, P5](../../principles.md) y las tensiones "datos honestos frente a métricas como meta" y "no afirmar lo que no se midió".
- **Relacionados:** [0011](../0011-cache-compartida-entre-maquinas/README.md) (la caché se reconstruye desde los comentarios), [0014](../0014-contextos-y-perfiles-personal-y-trabajo/README.md) (dónde vive la verdad del tiempo), [0021](../0021-arquitectura-de-lectura-consultas-y-vistas/README.md) (modelo de lectura), [0025](../../decisions/0025-contrato-json-de-lectura.md) (contrato JSON solo aditivo), [defecto 0022](../../defects/0022-sync-presenta-valores-por-defecto-como-medidos.md) (valores por defecto presentados como medidos), [reporte-ideal](../0005-vista-personal-agenda-y-backlog/reporte-ideal.md).
- **Documentos de esta carpeta:** [`analisis.md`](./analisis.md) (evidencia, alternativas y críticas), [`plan-por-fases.md`](./plan-por-fases.md) (qué se cambia, en qué orden y cómo se verifica).

> **Aviso de datos (decisión [0007](../../decisions/0007-documentos-agnosticos-de-instancia.md)).** Todos los números, tickets y tracks de este RFC son de ejemplo. Los datos reales que motivaron la propuesta viven fuera del repositorio.

## Para qué existe la herramienta (lo que este RFC quiere cumplir)

El registro de tiempo y de tickets existe para saber **en dónde se va el tiempo** y comprobar si coincide con el plan que la persona se ha fijado. Un plan de ejemplo, que es el que se usa a lo largo de este RFC:

| Clase | Plan de ejemplo |
| :--- | ---: |
| Requerimientos funcionales nuevos (`feature`) | 50 % |
| Soporte (`soporte`) | 30 % |
| Deuda técnica (`deuda`) | 15 % |
| Aprendizaje (`aprendizaje`) | 5 % |

El plan es **de la persona, no de la herramienta**: sus valores viven en configuración local y pueden cambiar. Que la herramienta pueda compararlo con lo registrado también es gestión de expectativas (P5): si buena parte de la jornada se va en reuniones, el 50 % de features no es el 50 % del reloj, y el reporte debe decirlo.

## Problema

Verificado sobre el código y una base local real (ver [`analisis.md`](./analisis.md) §1):

1. **El plan no existe en ningún documento ni en el código.** `principles.md` no tiene porcentajes. Existen otras tres fuentes de metas que no coinciden entre sí ni con el plan (dos documentos de `references/` y un maquetado en `reporte-ideal.md`) y **ningún código las lee**.
2. **`report time` no compara con nada.** Suma minutos por día, por proyecto y por balde de capacidad. No hay porcentajes, objetivo, desvío ni ventana.
3. **La taxonomía actual (`capacity_bucket`, 6 valores) no responde a la pregunta del plan.** `deep_work` mezcla features con fixes de soporte; `coordination` mezcla reuniones, preventas y administración; casi nada cae en `toil_support`. El resultado es que el reporte muestra "dónde se fue el tiempo" con una categoría que no es la que se quiere medir.
4. **`phase` y `role` no aportan señal:** valen lo mismo en todas las filas y la caché ya los marca como valor por defecto.
5. **El "AI Leverage Multiplier" no mide delegación**, solo el solape de intervalos (suma de duraciones dividida por la unión de intervalos del día). Presentarlo como productividad afirma algo que no se midió.
6. **El tiempo de agentes (`worker_type = agent:*`) se suma al humano** en el reparto por balde, lo que distorsiona cualquier porcentaje.
7. **Nadie dice cuánto de la jornada no se registró.** Un "30 % soporte" calculado sobre 20 horas registradas de 40 no significa lo mismo que sobre 38.

## Decisiones propuestas (cerradas salvo las marcadas como pendientes)

Cada una se justifica en [`analisis.md`](./analisis.md). Las marcadas **[PENDIENTE]** requieren que la persona decida antes de la Fase 1; se indica el valor por defecto con el que se continuaría.

### D1 · Clases de trabajo

Cinco clases, cerradas, con subtipos solo en `overhead`:

| Clase | Qué es | Cuenta para el plan |
| :--- | :--- | :---: |
| `feature` | Trabajo planificado que añade o cambia comportamiento del producto (incluye QA de esa entrega y spikes de diseño de una feature). | Sí |
| `soporte` | Demanda reactiva: incidentes, correcciones de producción, consultas y tareas rápidas de usuarios. | Sí |
| `deuda` | Trabajo que reduce coste futuro sin cambiar comportamiento visible: refactor, pruebas, herramientas del equipo, observabilidad. | Sí |
| `aprendizaje` | Estudio, exploración y pruebas de concepto sin entrega comprometida. | Sí |
| `overhead` (`reunion`, `preventa`, `admin`) | Coordinación y gestión que no es trabajo de ingeniería. | No: línea aparte |

**[PENDIENTE]** dónde caen `[SPIKE]` y `[QA]`. Por defecto: `[QA]` → `feature`; `[SPIKE]` → `aprendizaje`, salvo que la persona lo marque como `soporte` cuando investiga un incidente.
**[PENDIENTE]** herramientas y dotfiles propios: por defecto `deuda` si sirven al equipo, `aprendizaje` si son exploración personal.

### D2 · La clase se deriva al leer y solo se guarda lo declarado

- Una tabla versionada en configuración local (`classes.json`) traduce **prefijo de fase del título** y **etiquetas** a clase. Precedencia: **override por registro > etiqueta > prefijo de fase**.
- Lo **derivado nunca se escribe**: se recalcula en cada lectura. Así un cambio de título o de etiquetas se refleja sin migrar nada.
- Lo **declarado** (`--class` en `comment add` / `comment edit`) sí se guarda, como campo opcional `work_class` del bloque oculto del comentario (esquema 2.3, aditivo) y en una columna nullable de `worklogs`. Al viajar en el comentario, sobrevive a `report time --refresh` y a otra máquina (RFC 0011).
- En los **tickets paraguas** (`OPS`) no hay clase derivable, porque un mismo paraguas mezcla reuniones, preventas y soporte: `--class` es **obligatorio**, sin valor por defecto.
- Un ticket cuyo prefijo y etiqueta chocan (por ejemplo `[FEAT]` con etiqueta `deuda-tecnica`) **no se resuelve por regla**: se pregunta al registrar y se guarda el override.
- Cada fila lleva su **proveniencia** (`declared`, `derived`, `unclassified`); lo que no se pudo clasificar se muestra como `sin clasificar`, nunca se adivina.

### D3 · Base de cálculo y overhead

- La cifra principal compara con el plan **sobre tiempo de ingeniería humano registrado** (`feature + soporte + deuda + aprendizaje`).
- El `overhead` **no se prorratea ni se suma a soporte**: es una línea propia con su desglose. Prorratearlo escondería lo que cuestan las reuniones; sumarlo a soporte inflaría soporte y culparía al lugar equivocado.
- La **capacidad efectiva para features** se muestra como línea derivada: `plan_feature × (1 − overhead%)`, donde `overhead%` es el overhead dividido por el tiempo registrado total.
- Se muestra siempre la **cobertura**: tiempo registrado dividido por la jornada base configurable (480 min por día por defecto). Sin cobertura, ningún porcentaje es interpretable.
- Solo cuenta **tiempo humano de reloj** (unión de intervalos, sin sumar duraciones solapadas). El esfuerzo de agentes (`agent:*`) se muestra aparte y no entra en los porcentajes.
- **[PENDIENTE]** si las filas `agent:*` que la persona considera tiempo propio (estuvo presente) deben contarse como humano. Esta decisión cambia todos los porcentajes de las semanas ya registradas; hasta decidirla, esas filas se muestran aparte.

### D4 · Qué comunica el reporte (y qué no)

- Desviación **neutra**, con flecha y puntos porcentuales; **sin semáforos de color** (tensión Goodhart de `principles.md`: tendencias, no puntajes).
- Para `deuda` y `aprendizaje`, cuyo peso es pequeño, la tolerancia se expresa en **horas absolutas** (±2 h por semana por defecto) y no en puntos porcentuales: ±5 pp sobre un 5 % de plan es un 100 % de error relativo.
- **No concluyente**: una ventana con menos de 20 h de ingeniería lo declara, y no muestra ninguna desviación como problema.
- El texto lo produce la herramienta a partir de claves guardadas. Un agente que narra el reporte **no inventa etiquetas** ("Diagnóstico", "Despliegue"…): usa las clases tal cual salen del reporte.
- El "AI Leverage Multiplier" sale del bloque principal; si se conserva, se renombra a **"solape de intervalos"**, porque es lo único que mide.

### D5 · Dónde vive cada cosa

| Qué | Dónde | Por qué |
| :--- | :--- | :--- |
| Principio general (sin números) | `docs/principles.md`, nuevo **P6** | El repo es público y agnóstico de instancia (0007) |
| Valores del plan (50/30/15/5, tolerancias, jornada, mínimo de muestra) | `~/.config/plane/targets.json` (local) | Son de la persona y cambian |
| Tabla fase/etiqueta → clase | `~/.config/plane/classes.json` (local, con versión) | Es convención de la persona; debe poder cambiar sin tocar el código |
| Regla de uso (`--class` en paraguas) | `~/.claude/CLAUDE.md` y `SKILL.md` | Es operativa para el agente |
| Metas viejas de `references/` | Se retiran | Hoy contradicen el plan |

Texto propuesto para el principio, sin porcentajes:

> **P6 · Distribución declarada.** La persona define cómo quiere repartir su tiempo y la herramienta compara lo registrado con ese plan. Las desviaciones se muestran como información, no como juicio; lo que no se registró o no se clasificó se dice, nunca se rellena.

### D6 · Qué NO se hace en esta iniciativa

| Descartado o diferido | Motivo |
| :--- | :--- |
| Retirar `capacity_bucket` | Gobierna comportamiento (`NO_PROPOSAL_BUCKETS`: sin propuesta de duración en `toil_support` y `coordination`); retirarlo exige migrar esa lógica y subir el contrato a `plane-tracker/2`. Convive como eje histórico y de comportamiento. |
| Retirar `phase` y `role` | Son aditivos; quitarlos de `results[]` es un cambio de contrato (0025). Diferido hasta `plane-tracker/2`. |
| Reescribir en Plane los comentarios ya publicados | Riesgo de duplicar o corromper el bloque oculto, y viola "una sola fuente de verdad por dato". Las filas históricas se clasifican en lectura; solo se edita un comentario si la persona lo pide, uno a uno. |
| Ventana móvil de 4 semanas y proyección semanal | Con pocos días de datos no son significativas. Diferidas hasta tener al menos 3 semanas registradas. |
| Persistir la clase derivada | Congela errores de un default y obliga a migrar para corregirlos. |

## Mockup del bloque de reporte (datos de ejemplo)

```
ASIGNACIÓN · semana 45 · tiempo humano · 31 h registradas (cobertura 78 % de 40 h)

Ingeniería (22 h)        real    plan    desvío
  feature                 41 %    50 %    -9 pp  ↓
  soporte                 45 %    30 %   +15 pp  ↑
  deuda                   14 %    15 %    -1 pp
  aprendizaje              0 %     5 %    -1,1 h

Overhead (9 h = 29 % de lo registrado): reunión 2 h · preventa 4 h · admin 3 h
Capacidad efectiva para features: 50 % × (1 − 0,29) = 35 % de lo registrado
Sin clasificar: 0 h · Agentes (aparte): 3,2 h
Nota: menos de 20 h de ingeniería en la ventana; no concluyente.
```

Forma del JSON (aditiva sobre `plane-tracker/1`, ver 0025): `summary.allocation = { basis, human_minutes, coverage, engineering: { feature|soporte|deuda|aprendizaje: { minutes, pct, plan_pct, delta } }, overhead: { reunion, preventa, admin }, unclassified_minutes, agent_minutes, conclusive }`.

## Riesgos

- **Goodhart:** convertir 50/30/15/5 en una meta invita a reclasificar para "cumplir". Mitigación: desviación neutra, sin color, y la proveniencia de cada fila visible.
- **Sesgo al clasificar:** la clase por defecto sale del ticket y todo override queda marcado como declarado.
- **Fricción de registro:** un flag más en paraguas. Mitigación: es el único sitio donde no se puede derivar; en tickets de proyecto no hay flag.
- **Fuente de verdad del tiempo sin resolver (RFC 0014):** el diseño no depende de ella, porque lo declarado viaja en el bloque oculto y lo derivado se recalcula.

## Criterio de cierre

- Las decisiones **[PENDIENTE]** registradas por escrito y este RFC en `propuesto` → `aceptado`.
- Fases 1, 2, 3 y 5 de [`plan-por-fases.md`](./plan-por-fases.md) hechas y sus criterios de aceptación cumplidos; entonces el estado pasa a `implementado` (la Fase 4 queda como RFC o issue aparte).
