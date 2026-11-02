"""Texto de la vista `worklog check`: un render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el entorno. Las inconsistencias (duplicate, orphan, mismatch, missing_local) cuentan como errores; el resto, como avisos.
"""

from plane_cli import vocabulary


def render(doc):
    period, summary = doc["scope"]["period"], doc["summary"]
    errors = vocabulary.CHECK_ERROR_CODES
    lines = [f"\n🔎 Consistencia worklogs ↔ comentarios · {period['from']} → {period['to']}"]
    if not summary["checked"] and not summary["unreachable"]:
        lines.append("   (no hay worklogs locales en el periodo)")
    for item in summary["checked"]:
        found = [i for i in doc["results"] if i["ticket"] == item["ticket"] and i["code"] != "unreachable"]
        lines.append(f"   {'✖' if [i for i in found if i['code'] in errors] else '✔'} {item['ticket']}: {item['worklogs']} worklog(s)")
        lines += [f"      [{i['code']}] {i['detail']}" + (f"  ({i['comment_id'][:8]})" if i.get("comment_id") else "") for i in found]
    lines += [f"   ? {i['ticket']}: {i['detail']}" for i in doc["results"] if i["code"] == "unreachable"]
    n_errors = sum(1 for i in doc["results"] if i["code"] in errors)
    lines.append(f"\n   Resumen: {n_errors} inconsistencia(s), {doc['total'] - n_errors} aviso(s). Solo lectura: corrige con comment edit o report time --refresh.\n")
    return "\n".join(lines) + "\n"
