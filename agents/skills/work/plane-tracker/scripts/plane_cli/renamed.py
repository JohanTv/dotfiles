"""Pistas para nombres de comando retirados, verbos faltantes o mal escritos.

Expone: suggestion(argv, tree).
No hace: ejecutar nada ni registrar alias; solo devuelve el texto de error (o None) que cli.main() imprime con
código 2 antes de validar el entorno. No importa cli: recibe el árbol `{comando: (verbos)|()}` ya calculado.
"""

import difflib
import shlex

# Formas retiradas: nombre plano -> (grupo, verbo).
RETIRED = {"comment-edit": ("comment", "edit"), "comment-delete": ("comment", "delete"),
           "propose-duration": ("worklog", "propose"), "attach": ("attachment", "add"), "attachments": ("attachment", "list")}
# Sinónimos habituales de cada verbo.
SYNONYMS = {"create": "add", "new": "add", "post": "add", "rm": "delete", "remove": "delete", "del": "delete",
            "ls": "list", "show": "list", "update": "edit", "modify": "edit", "off": "clear", "stop": "clear", "unset": "clear",
            "on": "set", "start": "set", "send": "flush", "publish": "flush", "sync": "flush", "push": "flush", "discard": "drop"}
# Ejemplo de uso por grupo cuando no hay argumentos de los que partir.
EXAMPLES = {"comment": "comment add OPS-13 -m x --duration 5", "attachment": "attachment list OPS-13",
            "link": "link add OPS-13 https://example.com", "focus": "focus set OPS-13", "worklog": "worklog propose OPS-13",
            "outbox": "outbox flush"}
EDIT_FLAGS = ("--comment-id", "--embed-metadata", "--force")
HELP_FLAGS = ("-h", "--help")


def _drop(tokens, spec):
    """Quita de `tokens` los flags de `spec` ({flag: número de valores}), también en la forma `--flag=valor`."""
    out, i = [], 0
    while i < len(tokens):
        flag = tokens[i].split("=", 1)[0]
        if flag in spec:
            i += 1 if "=" in tokens[i] else 1 + spec[flag]
        else:
            out.append(tokens[i])
            i += 1
    return out


def _value(tokens, flag):
    """Valor de `--flag VALOR` o `--flag=VALOR`, o None si falta."""
    for i, token in enumerate(tokens):
        if token == flag:
            return tokens[i + 1] if i + 1 < len(tokens) and not tokens[i + 1].startswith("-") else None
        if token.startswith(flag + "="):
            return token.split("=", 1)[1]
    return None


def _positionals(tokens):
    return [t for t in tokens if not t.startswith("-")]


def _retired(old, argv):
    return f"'{old}' ya no existe; usa: plane-tracker {shlex.join(argv)}"


def _report(prefix, rest):
    """`report --check|--flow|--sync` -> `worklog check`, `report flow`, `report --refresh`."""
    if "--check" in rest:
        kept = _drop(rest, {"--check": 0, "--flow": 0, "--sync": 0, "--refresh": 0, "--track": 1, "--worker-type": 1})
        return _retired("report --check", [*prefix, "worklog", "check", *kept])
    labels = [name for flag, name in (("--flow", "report --flow"), ("--sync", "--sync")) if flag in rest]
    if not labels:
        return None
    kept = ["--refresh" if t == "--sync" else t for t in rest if t != "--flow"]
    return _retired(labels[0], [*prefix, "report", *(["flow"] if "--flow" in rest else []), *kept])


def _attachment(prefix, cmd, rest, verbs):
    """`attach` y `attachments` -> `attachment add|list|delete|replace`."""
    core = [t for t in rest if t != "--json"]
    if core and core[0] in verbs:
        return _retired(cmd, [*prefix, "attachment", *rest])
    if cmd == "attach" and _has(rest, "--replace"):
        pos = _positionals(_drop(rest, {"--replace": 1, "--json": 0}))
        ident = _value(rest, "--replace") or "ID"
        files = pos[1:] or ["FILE"]
        return _retired("attach --replace", [*prefix, "attachment", "replace", pos[0] if pos else "ISSUE", ident, *files])
    if cmd == "attachments" and _has(rest, "--delete"):
        pos = _positionals(_drop(rest, {"--delete": 1, "--json": 0}))
        return _retired("attachments --delete", [*prefix, "attachment", "delete", pos[0] if pos else "ISSUE", _value(rest, "--delete") or "ID"])
    return _retired(cmd, [*prefix, "attachment", RETIRED[cmd][1], *rest])


def _has(tokens, flag):
    return any(t == flag or t.startswith(flag + "=") for t in tokens)


def _focus(prefix, rest):
    """`focus --off|--status|TICKET` -> `focus clear|status|set`."""
    for flag, verb in (("--off", "clear"), ("--status", "status")):
        if flag in rest:
            return _retired(f"focus {flag}", [*prefix, "focus", verb, *_drop(rest, {"--off": 0, "--status": 0})])
    return None


def _missing_verb(prefix, group, verbs, rest):
    """Hint cuando el grupo se invoca sin verbo: inserta el verbo evidente o muestra un ejemplo."""
    if group == "comment":
        verb = "edit" if any(_has(rest, f) for f in EDIT_FLAGS) else "add"
    else:
        verb = {"link": "add", "focus": "set"}.get(group)
    if rest and verb:
        example = shlex.join([*prefix, group, verb, *rest])
    else:
        example = EXAMPLES[group]
    return f"falta el verbo ({'|'.join(verbs)}); ej: plane-tracker {example}"


def _group(prefix, cmd, verbs, rest):
    core = [t for t in rest if t != "--json"]
    if not core:
        return _missing_verb(prefix, cmd, verbs, [])
    first = core[0]
    if first in verbs or first in HELP_FLAGS:
        return None
    hint = _focus(prefix, rest) if cmd == "focus" else None
    if hint:
        return hint
    if first in SYNONYMS:
        target = SYNONYMS[first]
        if target not in verbs:
            return None
        tail = list(rest)
        tail.remove(first)
        return f"'{cmd} {first}' no existe; usa: plane-tracker {shlex.join([*prefix, cmd, target, *tail])}"
    if not first.startswith("-"):
        close = difflib.get_close_matches(first, verbs, n=1)
        if close:
            return f"verbo '{first}' desconocido en '{cmd}'; ¿quisiste decir '{close[0]}'?"
    return _missing_verb(prefix, cmd, verbs, rest)


def suggestion(argv, tree):
    """Texto de error si `argv` usa un nombre retirado, no indica el verbo o lo escribe mal; None si no hay nada que corregir."""
    start = next((i for i, token in enumerate(argv) if token != "--json"), None)
    if start is None or argv[start].startswith("-"):
        return None
    prefix, cmd, rest = argv[:start], argv[start], argv[start + 1:]
    if cmd in tree:
        if tree[cmd]:
            return _group(prefix, cmd, tree[cmd], rest)
        return _report(prefix, rest) if cmd == "report" else None
    if cmd in ("attach", "attachments"):
        return _attachment(prefix, cmd, rest, tree.get("attachment", ()))
    if cmd in RETIRED:
        group, verb = RETIRED[cmd]
        return _retired(cmd, [*prefix, group, verb, *rest])
    close = difflib.get_close_matches(cmd, tree, n=1)
    return f"comando '{cmd}' desconocido; ¿quisiste decir '{close[0]}'?" if close else None
