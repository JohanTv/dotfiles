# Reporte ideal: `agenda`

Maqueta de la vista personal que propone el [RFC 0005](./README.md). Es de lectura rápida, local y **no envía nada**: la persona decide qué comparte (principio P2). Los tickets del ejemplo son ficticios.

## Maqueta

```text
AGENDA · <persona> · 2026-10-31   (sincronizado con Plane hace 3 min)

CARGA   En curso: 5 (límite sugerido 3) · En revisión: 1 · Vencidos: 3 · Sin movimiento >7 d: 2

1  EN CURSO (compromisos)                prio     vence         edad   último movimiento
   PROJ-136 Módulo de correos            urgent   16/10 ⚠ -15d  30 d   hace 9 d
   PROJ-144 Migración de runtime         urgent   —             12 d   hace 1 d
   OPS-13   Configurar firma de correo   urgent   30/10 ⚠ -1 d  3 d    hace 1 d    ← ¿caso de toil <15 min?
   OPS-11   Preparar solicitudes         medium   30/10 ⚠ -1 d  5 d    hace 2 d
   PROJ-141 Redes sociales               none     —             20 d   hace 6 d

2  SIGUIENTE (pendiente y en revisión)
   PROJ-10  Refactor a monolito modular            medium   pendiente
   PROJ-205 Linter en el servicio de envío         low      en revisión, esperando al líder técnico

3  BACKLOG PROPIO (con motivo de diferimiento)
   PROJ-236 [high] diferido: capacidad (hay dos urgentes en curso) · revisar 2026-11-09
   PROJ-237 [high] diferido: depende de PROJ-236                   · revisar 2026-11-09
   PROJ-123 [low]  sin motivo registrado ⚠

4  TRABAJO INVISIBLE DE LA SEMANA
   soporte 0 h · coordinación 0 h   (meta: 20 % / 15 %)   ⚠ sin registrar

5  EXPECTATIVAS
   comprometido el lunes: 4 · cerrado: 1 · mediana de cycle time de [FIX]: 6 d
```

## De dónde sale cada sección

| Sección | Fuente | ¿Existe hoy? |
| :--- | :--- | :--- |
| Encabezado y "sincronizado hace" | Metadatos de sincronización de la caché | Parcial: se guarda la marca, no se muestra (defecto [0010](../../defects/0010-reporte-no-sincroniza-periodos-con-registros-parciales.md)) |
| Carga | Estado, antigüedad y `updated_at` de los tickets de la persona | No: falta el filtro por asignado (RFC 0005 fase 0) |
| En curso | Plane: `assignees`, `state`, `priority`, `target_date`, `created_at` | Datos sí; vista y filtros no |
| Siguiente | Plane: estados `Pendiente` y `Revisión` | Datos sí |
| Backlog con motivo | Comentario estructurado de diferimiento (RFC 0005 fase 2) | No |
| Trabajo invisible | Worklogs locales por balde de capacidad frente a la meta del balde | Datos sí (`capacity_bucket`); comparación no |
| Expectativas | Lo comprometido al inicio de la semana frente a lo cerrado; medianas de `report flow` | Medianas sí; comparación no |

## Reglas de diseño

- **Una sola pantalla.** Si no cabe, se resumen las secciones y se enlaza el detalle: la carga cognitiva de leer el reporte cuenta (P4).
- **Alertas con motivo, no con puntaje.** Un vencido muestra cuántos días lleva vencido y cuál es su último movimiento; nunca un porcentaje de cumplimiento (P5, ley de Goodhart).
- **Sin escritura.** `agenda` solo lee; compartir algo con quien supervisa es otra acción, explícita y filtrada (RFC 0005 fase 4).
- **Honestidad ante datos viejos.** Si la caché no está al día lo dice en la primera línea, y no presenta un resultado parcial como completo.
