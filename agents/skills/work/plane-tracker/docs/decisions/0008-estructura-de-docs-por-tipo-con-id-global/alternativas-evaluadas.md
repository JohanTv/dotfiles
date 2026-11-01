# Alternativas evaluadas para organizar `docs/`

Contexto de la [decisión 0008](./README.md). Se evaluaron las opciones con dos revisiones independientes de solo lectura (una favorable a una estructura completa desde el principio y otra escéptica, centrada en el tamaño real y en la privacidad), y se decidió por la visión a largo plazo.

## Problema

`issues/` mezclaba un defecto, una propuesta y un ítem híbrido, y `ROADMAP.md` apuntaba a ellos. Se esperaba que la herramienta creciera mucho y que reorganizar más tarde costara más que hacerlo antes.

## Opciones

| | Opción | Resumen |
| :--- | :--- | :--- |
| A | Todo en `issues/` con un campo `Tipo` | No mueve nada. Mezcla ítems de ciclo de vida distinto. |
| B | Carpetas hermanas por tipo en la raíz de la skill | `defects/`, `rfcs/`, `decisions/` junto a `SKILL.md`. |
| C | Una carpeta plana `work-items/` con front-matter | Un solo contenedor; el tipo en el front-matter; índice generado. |
| D | Subcarpetas por estado (`abiertos/`, `cerrados/`) | Cada cierre mueve el archivo. |
| E | **Elegida:** `docs/` con una carpeta por tipo, ID global y estado en el front-matter | `docs/defects`, `docs/rfcs`, `docs/decisions`; índice generado. |
| F | Plane como única fuente de los ítems de diseño | Tickets con adjuntos y casi ningún documento de proceso en el repositorio. |

## Evaluación

| Criterio | A | B | C | D | E (elegida) | F |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Ciclo de vida distinto por tipo (defecto se cierra, ADR es permanente) | Mal | Bien | Regular | Mal | **Bien** | Bien |
| Descubribilidad a 100 ítems | Mal | Bien | Regular | Regular | **Bien** | Depende de Plane |
| Cerrar un ítem no rompe enlaces | Sí | Sí | Sí | **No** (cada cierre es un `git mv`) | **Sí** | Sí |
| No añade directorios junto a `SKILL.md` | Sí | No | Sí | Sí | **Sí** (todo bajo `docs/`) | Sí |
| Choque de vocabulario con Plane (`issues`, `work-items`) | Sí (`issues`) | Sí | Sí (`work-items`) | — | **No** | — |
| Documentos propios de la herramienta en la propia herramienta | Sí | Sí | Sí | Sí | **Sí** | No: Plane no gestiona la herramienta |
| Reversibilidad | Alta | Alta | Alta | Media | **Alta** (`git mv` conserva el ID) | Alta |

## Decisiones derivadas

- **Numeración global única.** Los commits ya citaban "issue 0002"; renumerar por carpeta rompería `git log --grep`.
- **Estado en el front-matter**, no en la ubicación. Solo `implementado` y `corregido` autorizan a citar algo como existente.
- **Ítem con varios documentos = carpeta.** Añadido después de la primera propuesta: el contexto de un ítem (análisis, maquetas, alternativas) debe vivir con él.
- **Sin campo `ticket`.** Plane no gestiona la herramienta, así que no hay ticket que enlazar.
- **Índice generado y comprobado por un test.** El revisor escéptico advirtió que el estado mantenido a mano en varios sitios ya había fallado una vez (un índice manual que no listaba un defecto abierto). Con un solo índice generado el desfase no puede pasar inadvertido.

## Lo que se difirió y su disparador

- **Archivar:** nada hasta unos 150 documentos cerrados; entonces el índice ocultará los cerrados por defecto.
- **Separar la skill del proyecto:** hoy no compensa (el `SKILL.md` ya hace divulgación progresiva y el enlace simbólico no cuesta tokens). Se reconsidera si `docs/` supera con claridad al contenido operativo, si aparece un segundo consumidor o si se quiere publicar el CLI por separado.

## Aviso sobre privacidad

La revisión escéptica señaló que el repositorio es público y que los documentos existentes contenían datos de instancia y de personas. Eso dio lugar a la [decisión 0007](../0007-documentos-agnosticos-de-instancia.md) y al saneamiento del historial.
