"""Texto de la vista `report flow`: un render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el entorno ni el reloj. Las notas (transiciones sin verificar, horas sin publicar...) van al final.
"""

from plane_cli import vocabulary
from plane_cli.timeutil import format_span


def _render_flow_markdown(doc):
    period = doc["scope"]["period"]
    lines = [f"# 🔁 Reporte de Flujo de Entrega (Lead & Cycle Time)\n",
             f"**Período:** `{period['from']}` → `{period['to']}` (calendario; lead/cycle en UTC)\n"]

    if not doc["results"]:
        lines.append("*(Sin tickets con worklogs en caché ni cerrados en el periodo)*\n")
    else:
        lines.append("### 📋 Detalle de Tickets\n")
        lines.append("| Estado | Ticket | Título | Lead Time | Cycle Activo | Standby | Esfuerzo (Reloj / Cómputo) |")
        lines.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: |")
        for f in doc["results"]:
            outcome = {"completed": "✔", "cancelled": "✖", "open": "…"}.get(f["outcome"], "?")
            flags = f" `[{', '.join(f['flags'])}]`" if f["flags"] else ""
            raw_title = f.get("title") or ""
            t_title = raw_title.replace("|", "\\|").replace("\n", " ").strip()
            standby_val = f"⏸ {format_span(f['standby_minutes'])}" if (f.get("standby_minutes") or 0.0) > 0 else "—"
            effort_str = f"{format_span(f['effort_clock_minutes'])} / {format_span(f['effort_compute_minutes'])}"
            lines.append(f"| {outcome} | `{f['ticket']}` | {t_title[:60]}{flags} | {format_span(f['lead_minutes'])} | {format_span(f['cycle_active_minutes'])} | {standby_val} | {effort_str} |")
        lines.append("")

        agg = doc["summary"]
        lines.append("### 📊 Resumen Métrico de Flujo\n")
        lines.append(f"- **Tickets:** {agg['completed']} completados · {agg['cancelled']} cancelados · {agg['open']} abiertos ({agg['excluded']} excluidos)")
        lines.append(f"- **Mediana Lead Time:** `{format_span(agg['median_lead_minutes'])}` (n={agg['n_lead']})")
        lines.append(f"- **Mediana Cycle Time (Activo):** `{format_span(agg['median_cycle_minutes'])}` (n={agg['n_cycle']})")
        if (agg.get("total_standby_minutes") or 0.0) > 0:
            lines.append(f"- **Standby Total Acumulado:** `{format_span(agg['total_standby_minutes'])}` ({agg.get('tickets_with_standby') or 0} ticket(s) · Mediana: `{format_span(agg.get('median_standby_minutes') or 0)}`)")
        lines.append("")

    notes = [f"> {'⚠' if vocabulary.NOTES[n['code']][0] == 'warn' else 'ℹ'} {n['text']}" + (f" → {n['hint']}" if n.get("hint") else "") for n in doc["notes"]]
    if notes:
        lines.append("### ℹ️ Observaciones\n")
        lines.extend(notes)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render(doc, markdown=False):
    if markdown:
        return _render_flow_markdown(doc)
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
