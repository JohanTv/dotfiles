"""Texto de las vistas de catálogo `labels` y `projects`, a partir del sobre.

Expone: render_labels(), render_projects().
No hace: consultar ni leer el entorno. Las notas (datos vencidos) van al final.
"""

from plane_cli import vocabulary


def _notes(doc):
    return [f"  {'⚠' if vocabulary.NOTES[n['code']][0] == 'warn' else 'ℹ'} {n['text']}" + (f" → {n['hint']}" if n.get("hint") else "") for n in doc["notes"]]


def render_labels(doc):
    project = ", ".join(doc["scope"].get("projects") or [])
    lines = [f"\n🏷  Etiquetas disponibles para el proyecto {project} ({doc['total']}):"]
    lines += [f"  • {r['name']:<18} {'(' + r['color'] + ')' if r.get('color') else ''}" for r in doc["results"]]
    return "\n".join(lines + _notes(doc) + ["\n💡 Úsalas en: plane-tracker create ... --labels 'backend,bug'\n"]) + "\n"


def render_projects(doc):
    lines = [f"\n📂 Proyectos del workspace ({doc['total']}):"] + [f"  • {r['identifier']:<14} ➔  {r['name']}" for r in doc["results"]]
    return "\n".join(lines + _notes(doc) + ["\n💡 Usa 'plane-tracker projects --refresh' para forzar la sincronización con el servidor Plane.\n"]) + "\n"
