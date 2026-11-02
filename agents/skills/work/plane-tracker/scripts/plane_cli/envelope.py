"""Sobre JSON versionado `plane-tracker/1` de las lecturas: construcción, validación contra el vocabulario y serialización.

Expone: build(), validate(), validate_error(), dumps().
No hace: consultar, renderizar ni imprimir. Valida en las pruebas (F3) y, en producción, una deriva (campo fuera del vocabulario, cobertura
incoherente) NO tumba el comando: el sobre sale igual con la nota `internal` y `complete` degradado a None, para que un agente reciba datos y un
humano vea el defecto. En la fase 0 el alcance es un dict ya resuelto (el dataclass Scope llega con la fase 1).
"""

import json

from plane_cli import coverage, vocabulary

_TYPES = {"str": (str,), "int": (int,), "num": (int, float), "bool": (bool,), "list": (list,), "dict": (dict,)}
F14 = "complete es true con una nota de severidad warn"


def _type_problems(where, value, spec):
    kind, nullable, _required = vocabulary.field_spec(spec)
    if value is None:
        return [] if nullable else [f"{where}: no admite null"]
    ok = isinstance(value, _TYPES[kind]) and not (kind in ("int", "num") and isinstance(value, bool))
    return [] if ok else [f"{where}: se esperaba {kind}"]


def _fields_problems(where, doc, fields, allowed_only=True):
    """Claves de `doc` dentro de `fields` (nombre -> especificación), con tipos y obligatorias presentes."""
    problems = [f"{where}: clave fuera del vocabulario: {key}" for key in sorted(doc) if key not in fields] if allowed_only else []
    for key, spec in fields.items():
        if key in doc:
            problems += _type_problems(f"{where}.{key}", doc[key], spec)
        elif vocabulary.field_spec(spec)[2]:
            problems.append(f"{where}: falta la clave obligatoria {key}")
    return problems


def _row_problems(where, row, family):
    if not isinstance(row, dict):
        return [f"{where}: la fila debe ser un objeto"]
    problems = _fields_problems(where, row, vocabulary.FAMILIES[family])
    for key, allowed in vocabulary.NESTED.items():
        for i, item in enumerate(row.get(key) or []):
            extra = sorted(set(item) - allowed) if isinstance(item, dict) else ["(no es objeto)"]
            problems += [f"{where}.{key}[{i}]: clave fuera del vocabulario: {name}" for name in extra]
    if isinstance(row.get("flow"), dict):
        flow_fields = {k: v for k, v in vocabulary.FAMILIES["flow"].items() if k not in ("ticket", "title")}
        problems += _fields_problems(f"{where}.flow", row["flow"], {k: v.rstrip("!") for k, v in flow_fields.items()})
    return problems


def _summary_problems(summary, family):
    if summary is None:
        return []
    if family is None:
        return ["summary: esta vista no lleva agregados"]
    problems = _fields_problems("summary", summary, {k: v.rstrip("!") for k, v in vocabulary.SUMMARIES[family].items()})
    if family == "hours_summary":
        for key in ("by_day", "by_project", "by_capacity"):
            for i, item in enumerate(summary.get(key) or []):
                problems += [f"summary.{key}[{i}]: clave fuera del vocabulario: {name}" for name in sorted(set(item) - vocabulary.SUMMARY_ITEM_KEYS)]
    return problems


def _scope_problems(scope):
    problems = [f"scope: clave fuera del vocabulario: {key}" for key in sorted(scope) if key not in vocabulary.SCOPE_KEYS]
    person = scope.get("ticket_person")
    if person and person.get("relation") not in vocabulary.PERSON_RELATIONS:
        problems.append(f"scope.ticket_person.relation: no es una relación válida: {person.get('relation')}")
    if "state" in scope and scope["state"] not in vocabulary.STATES:
        problems.append(f"scope.state: no es un estado válido: {scope['state']}")
    return problems


def _coverage_problems(cov):
    problems = _fields_problems("coverage", cov, vocabulary.COVERAGE_KEYS)
    if cov.get("source") not in vocabulary.COVERAGE_SOURCES:
        problems.append(f"coverage.source: origen no válido: {cov.get('source')}")
    problems += [f"coverage.detail: clave fuera del vocabulario: {key}" for key in sorted(cov.get("detail") or {}) if key not in vocabulary.DETAIL_KEYS]
    return problems


def _note_problems(i, note):
    where = f"notes[{i}]"
    if not isinstance(note, dict):
        return [f"{where}: la nota debe ser un objeto"]
    problems = _fields_problems(where, note, vocabulary.NOTE_KEYS)
    entry = vocabulary.NOTES.get(note.get("code"))
    if entry is None:
        return problems + [f"{where}: código de nota no registrado: {note.get('code')}"]
    if entry[0] == "warn" and not note.get("hint"):
        problems.append(f"{where}: un aviso necesita hint")
    return problems


def validate(doc):
    """Lista de problemas del sobre de lectura frente al vocabulario (vacía si es válido)."""
    if not isinstance(doc, dict):
        return ["el sobre debe ser un objeto"]
    view = doc.get("view")
    if view not in vocabulary.VIEWS:
        return [f"view: vista no registrada: {view}"]
    family, summary_family, has_scope = vocabulary.VIEWS[view]
    fields = dict(vocabulary.ENVELOPE_KEYS)
    if has_scope:
        fields["scope"] += "!"
    problems = _fields_problems("sobre", doc, fields)
    if doc.get("schema") != vocabulary.SCHEMA:
        problems.append(f"schema: se esperaba {vocabulary.SCHEMA}")
    if not has_scope and "scope" in doc:
        problems.append("scope: esta vista no lleva alcance")
    if problems:
        return problems
    scope = doc.get("scope") or {}
    problems += _scope_problems(scope) + _coverage_problems(doc["coverage"]) + _summary_problems(doc["summary"], summary_family)
    for i, row in enumerate(doc["results"]):
        problems += _row_problems(f"results[{i}]", row, family)
    for i, note in enumerate(doc["notes"]):
        problems += _note_problems(i, note)
    limit = scope.get("limit")
    if doc["count"] != len(doc["results"]) or doc["count"] > doc["total"]:
        problems.append("count debe ser len(results) y no mayor que total")
    elif limit is not None and doc["count"] > limit:
        problems.append("count excede el límite del alcance")
    elif limit is None and doc["count"] != doc["total"]:
        problems.append("sin límite, count debe ser igual a total")
    if doc["coverage"].get("complete") is True and any(vocabulary.NOTES.get(n.get("code"), ("",))[0] == "warn" for n in doc["notes"] if isinstance(n, dict)):
        problems.append(F14)
    return problems


def validate_error(doc):
    """Problemas del sobre de error frente al registro (vacía si es válido)."""
    if not isinstance(doc, dict):
        return ["el sobre de error debe ser un objeto"]
    problems = _fields_problems("error", doc, vocabulary.ERROR_KEYS)
    if doc.get("schema") != vocabulary.SCHEMA or doc.get("status") != "error":
        problems.append("error: schema o status incorrectos")
    if doc.get("code") not in vocabulary.ERRORS:
        problems.append(f"error: código no registrado: {doc.get('code')}")
    elif doc.get("exit") != vocabulary.ERRORS[doc["code"]]:
        problems.append("error: la salida no coincide con la del registro")
    return problems


def build(view, scope, result, verbose=False):
    """Sobre de una vista a partir de su alcance (dict o None, como `get`) y su Result; degrada con la nota `internal` si detecta deriva."""
    doc = {"schema": vocabulary.SCHEMA, "view": view, "total": result.total, "count": len(result.rows), "results": [dict(r) for r in result.rows],
           "summary": result.summary, "coverage": result.coverage.to_dict(),
           "notes": coverage.build_notes(result.coverage, scope, result, verbose)}
    if scope is not None:
        doc["scope"] = scope
    problems = validate(doc)
    if problems:
        text = "Deriva del sobre: " + "; ".join(problems[:3]) + (f" (+{len(problems) - 3})" if len(problems) > 3 else "")
        doc["notes"] = sorted(doc["notes"] + [{"code": "internal", "text": text, "hint": vocabulary.NOTES["internal"][3]}],
                              key=lambda n: (vocabulary.SEVERITY_ORDER.index(vocabulary.NOTES[n["code"]][0]), n["code"]))
        if doc["coverage"].get("complete") is True:
            doc["coverage"]["complete"] = None
    return doc


def dumps(doc):
    """Serialización compacta y determinista: mismo estado, mismos bytes."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
