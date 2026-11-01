# Principios de diseño de plane-tracker

Estos principios orientan qué se construye y cómo. No son operativos para un agente que usa la herramienta; los RFC y las decisiones los citan por su ancla. Todo lo que entra en este repositorio es público: ver [0007](./decisions/0007-documentos-agnosticos-de-instancia.md).

## P1 · Visibilidad del trabajo invisible
El soporte, las reuniones, las interrupciones y la coordinación son trabajo real. Si no se registran, desaparecen del radar y quien los hace parece inactivo. La herramienta debe hacer barato registrarlos (un comando) y mostrarlos junto al trabajo de ingeniería.

## P2 · Autonomía
La persona decide qué se registra, cuándo y qué se comparte. Nada se envía de forma automática, nada se estima en su nombre y la medición lee solo marcas de tiempo, no contenido.

## P3 · Datos para quien trabaja, no solo para quien supervisa
Cada dato que la herramienta captura debe servirle primero a quien lo genera: saber qué tiene abierto, qué está vencido, dónde se fue la semana. El reporte hacia arriba es una vista derivada y decidida por esa persona.

## P4 · Carga cognitiva
Cuántas cosas abiertas lleva alguien en la cabeza es una magnitud que se puede medir y mostrar: trabajo en curso, antigüedad, tiempo sin movimiento. Los límites de trabajo en curso y las bitácoras cortas existen para reducirla.

## P5 · Gestión de expectativas
Lo prometido, lo posible y lo reportado deben coincidir. Una fecha comprometida que vence en silencio, o un reporte que afirma un dato sin fuente, rompen la confianza. Los pronósticos salen de datos propios (medianas de cycle time), no de estimaciones.

## Tensiones entre principios

| Tensión | Resolución |
| :--- | :--- |
| Visibilidad hacia arriba (P3) frente a autonomía (P2) | Vista personal completa; envío explícito, filtrado y confirmado. |
| Trabajo invisible (P1) frente a carga de registro (P4) | Tickets paraguas semanales y un comando por intervención; sin micro-tickets. |
| Datos honestos (P5) frente a métricas como meta | Mostrar tendencias, no puntajes; una métrica convertida en objetivo se manipula (ley de Goodhart). |
| Backlog frente a compromiso (P5) | Backlog es intención sin fecha; las fechas de compromiso van solo en lo que está en curso. |

## Principios técnicos complementarios
- **Trabajo en curso limitado (ley de Little):** el tiempo medio que tarda un ítem en completarse crece con la cantidad de ítems abiertos a la vez. Limitar lo que está en curso acorta cada entrega y reduce la carga cognitiva (P4). La herramienta debe mostrar cuánto hay en curso y cuánto lleva cada ítem abierto, y sugerir un límite, sin imponerlo (P2).
- **Local-first:** las lecturas responden con lo local y avisan su antigüedad; la red es para publicar.
- **Una sola fuente de verdad por dato:** el estado de un ticket vive en Plane; el estado de un documento de diseño, en su cabecera.
- **No afirmar lo que no se midió:** si no hay fuente, el reporte lo dice o calla.

## Cobertura actual

Qué cubre hoy la herramienta de cada principio y qué falta: [`rfcs/0005-vista-personal-agenda-y-backlog/cobertura-actual-de-principios.md`](./rfcs/0005-vista-personal-agenda-y-backlog/cobertura-actual-de-principios.md).
