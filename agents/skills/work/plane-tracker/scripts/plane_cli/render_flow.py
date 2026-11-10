"""Texto de la vista `report flow`: un render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el entorno ni el reloj. Las notas (transiciones sin verificar, horas sin publicar...) van al final.
"""

from plane_cli import vocabulary
from plane_cli.timeutil import format_span


def render(doc):
    period = doc["scope"]["period"]
    lines = [f"\n🔁 Flujo por ticket · {period['from']} → {period['to']} (calendario; lead/cycle en UTC)"]
    if not doc["results"]:
        lines.append("   (sin tickets con worklogs en caché ni cerrados en el periodo; `report time --refresh` trae a la caché los worklogs de Plane)\n")
    for f in doc["results"]:
        outcome = {"completed": "✔", "cancelled": "✖", "open": "…"}[f["outcome"]]
        flags = f" [{', '.join(f['flags'])}]" if f["flags"] else ""
        lines.append(f"  {outcome} {f['ticket']:<10} lead {format_span(f['lead_minutes']):<8} cycle {format_span(f['cycle_active_minutes']):<8} "
                     f"esfuerzo {format_span(f['effort_clock_minutes'])} reloj / {format_span(f['effort_compute_minutes'])} cómputo{flags}")
        standby_tag = f" · ⏸ Pausado {format_span(f['standby_minutes'])}" if (f.get("standby_minutes") or 0.0) > 0 else ""
        lines.append(f"      {(f.get('title') or '')[:70]}{standby_tag}")
    if doc["results"]:
        agg = doc["summary"]
        lines.append(f"\n   Resumen: {agg['completed']} completados · {agg['cancelled']} cancelados · {agg['open']} abiertos")
        standby_summary = ""
        if (agg.get("total_standby_minutes") or 0.0) > 0:
            standby_summary = f" · standby acumulado {format_span(agg['total_standby_minutes'])} ({agg.get('tickets_with_standby') or 0} ticket(s))"
        lines.append(f"   Mediana lead {format_span(agg['median_lead_minutes'])} (n={agg['n_lead']}) · cycle {format_span(agg['median_cycle_minutes'])} (n={agg['n_cycle']}){standby_summary}; "
                     f"{agg['excluded']} excluidos (umbrella, instant_close, no_transition)")
        lines.append("   Nota: el esfuerzo sale de los worklogs de la caché local; lo no registrado no aparece.\n")
    lines += [f"  {'⚠' if vocabulary.NOTES[n['code']][0] == 'warn' else 'ℹ'} {n['text']}" + (f" → {n['hint']}" if n.get("hint") else "") for n in doc["notes"]]
    return "\n".join(lines) + "\n"
