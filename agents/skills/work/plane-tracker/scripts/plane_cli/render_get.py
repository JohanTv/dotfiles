"""Texto de la vista `get`: un render del sobre `plane-tracker/1` (una fila `ticket_detail`), nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el reloj: "ahora" es `as_of + age_s` de la cobertura. Las notas (datos locales vencidos) van primero, como el aviso de antes.
"""

from datetime import datetime

from plane_cli.timeutil import format_minutes, format_span

LIMIT = 300  # caracteres de la descripción y de cada comentario si no hay --full
OUTCOMES = {"completed": "completado", "cancelled": "cancelado", "open": "abierto"}


def _when(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _cut(text, full):
    return text if full or len(text) <= LIMIT else text[:LIMIT - 3] + "..."


def _lifecycle(row, cov):
    created = _when(row.get("created_at"))
    if not created:
        return "Ciclo     : ?"
    completed = _when(row.get("completed_at"))
    seconds = (completed - created).total_seconds() if completed else _when(cov["as_of"]).timestamp() + (cov.get("age_s") or 0) - created.timestamp()
    days = seconds / 86400.0
    span = f"{days:.1f} días" if days >= 1 else format_minutes(int(seconds // 60))
    if completed:
        return f"Ciclo     : completado {completed.astimezone().strftime('%Y-%m-%d %H:%M')} (lead time {span})"
    return f"Ciclo     : abierto desde hace {span}"


def _flow(flow):
    out = ["", "🔁 Flujo (calendario; esfuerzo = worklogs locales + metadata en comentarios)", f"   • Resultado : {OUTCOMES[flow['outcome']]}",
           f"   • Lead time : {format_span(flow['lead_minutes'])}{' (hasta hoy)' if flow['outcome'] == 'open' else ''}",
           f"   • Cycle     : {format_span(flow['cycle_active_minutes'])} activo · {format_span(flow['cycle_gross_minutes'])} bruto (Pausado excluido del activo)",
           f"   • Esfuerzo  : {format_span(flow['effort_clock_minutes'])} reloj · {format_span(flow['effort_compute_minutes'])} cómputo ({flow['worklogs']} worklogs)"]
    if flow.get("effort_clock_over_cycle") is not None:
        out.append(f"   • Reloj/cycle: {flow['effort_clock_over_cycle']:.2f} (señal secundaria: espera de terceros y paralelismo la distorsionan)")
    if flow.get("by_state_minutes"):
        out.append("   • Estados   : " + " · ".join(f"{k} {format_span(v)}" for k, v in flow["by_state_minutes"].items()))
    if flow.get("worklogs_before_created") or flow.get("worklogs_after_closed"):
        out.append(f"   • Fuera de ventana: {flow['worklogs_before_created']} antes de crear · {flow['worklogs_after_closed']} después de cerrar")
    if flow.get("flags"):
        out.append("   • Flags     : " + ", ".join(flow["flags"]))
    out += [f"   {_when(t['at']).astimezone().strftime('%Y-%m-%d %H:%M')}  {t['from']} → {t['to']}" for t in flow.get("transitions", [])]
    return out + [""]


def render(doc, full=False):
    row, cov = doc["results"][0], doc["coverage"]
    lines = []
    for note in doc["notes"]:
        lines.append(f"\n⚠ {note['text']}" + (f" → {note['hint']}" if note.get("hint") else ""))
    if cov["detail"].get("metadata_only"):
        lines.append("   Solo metadatos del listado: sin descripción ni comentarios.")
    elif cov["source"] == "snapshot" and "comments" not in row:
        lines.append("   Esta copia no incluye comentarios.")
    lines += [f"\n📌 {row['ticket']}: {row['title']}", f"   • Estado    : {row['state']}", f"   • Prioridad : {row['priority'].upper()}",
              f"   • Creado el : {(row.get('created_at') or '?')[:10]}"]
    if row.get("start_date") or row.get("target_date"):
        lines.append(f"   • Plan      : {row.get('start_date') or '—'} → {row.get('target_date') or '—'}")
    lines += [f"   • {_lifecycle(row, cov)}", f"   • UUID      : {row.get('uuid')}"]
    if row.get("description"):
        lines += ["\n📄 Descripción:", f"   {_cut(row['description'], full)}"]
    if row.get("flow"):
        lines += _flow(row["flow"])
    comments = row.get("comments") or []
    if comments:
        total, shown = cov["detail"]["comments"]["total"], len(comments)
        lines.append(f"\n💬 Contexto de Relevo / Comentarios ({f'{shown} de {total}' if shown < total else total}):")
        for i, c in enumerate(comments, total - shown + 1):
            lines.append(f"   [{i}] ({(c.get('created_at') or '')[:16].replace('T', ' ')}): {_cut(c['text'], full)}")
    return "\n".join(lines) + "\n\n"
