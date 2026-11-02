"""Texto de la vista `list`: un render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar, leer el entorno ni el reloj; todo lo que muestra sale del sobre (la antigüedad, de coverage.age_s).
Con `complete` distinto de true avisa de la cobertura (None se muestra como "no verificada", nunca como completa).
"""

from plane_cli import vocabulary
from plane_cli.coverage import completeness_label
from plane_cli.timeutil import age_text

_LABELS = {"assigned": "asignados a ti", "created": "creados por ti", "involved": "en los que estás involucrado"}


def _where(scope):
    projects = scope.get("projects") or []
    return ", ".join(projects) if len(projects) <= 3 else f"{len(projects)} proyectos"


def _line(row):
    prio = f"[{row['priority'].upper()}]" if row.get("priority") else f"({row['state_group']})"
    out = [f"  • {row['ticket']:<12} {row['state']:<12} {prio:<9} {row['title'][:60]}"]
    if "assignees" in row:
        who = ", ".join(a["name"] for a in row["assignees"]) or "sin asignar"
        out.append(f"      ↳ asignados: {who}" + (f" · razones: {', '.join(row['reasons'])}" if row.get("reasons") else ""))
    return out


def render(doc):
    scope, cov = doc["scope"], doc["coverage"]
    person = (scope.get("ticket_person") or {}).get("relation")
    shown = f"{doc['count']} de {doc['total']}" if doc["count"] < doc["total"] else str(doc["total"])
    head = f" · caché de hace {age_text(cov['age_s'])}" if cov.get("age_s") is not None else ""
    if cov.get("complete") is not True:
        head += f" · cobertura {completeness_label(cov.get('complete'))}"
    label = f"{_LABELS[person]} " if person else ""
    text = f" con «{scope['text']}»" if scope.get("text") else ""
    lines = [f"\n📋 Tickets {label}en {_where(scope)}{text} ({shown}){head}:"]
    for row in doc["results"]:
        lines += _line(row)
    for note in doc["notes"]:
        if note["code"] == "truncated":
            continue  # la cabecera ya dice "N de M"
        mark = "⚠" if vocabulary.NOTES[note["code"]][0] == "warn" else "ℹ"
        lines.append(f"  {mark} {note['text']}" + (f" → {note['hint']}" if note.get("hint") else ""))
    return "\n".join(lines) + "\n"
