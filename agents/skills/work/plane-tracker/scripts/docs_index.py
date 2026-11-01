#!/usr/bin/env python3
"""Genera docs/INDEX.md a partir del front-matter de docs/{defects,rfcs,decisions}/NNNN-*.md.

Uso: docs_index.py [--check]   (--check no escribe: sale con 1 si INDEX.md no está al día)."""
import os
import re
import sys

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
INDEX = os.path.join(DOCS, "INDEX.md")
REQUIRED = ("id", "title", "status", "created", "summary")
# carpeta -> (título de sección, estados válidos)
KINDS = {
    "defects": ("Defectos", ("abierto", "corregido", "descartado")),
    "rfcs": ("RFC", ("borrador", "propuesto", "aceptado", "implementado", "rechazado", "reemplazado")),
    "decisions": ("Decisiones", ("aceptado", "reemplazado")),
}
FILE_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
HEADER = """# Índice de documentos de desarrollo

> Generado por `scripts/docs_index.py`; no se edita a mano. Un RFC solo existe en el código si su estado es
> `implementado`; un defecto solo está resuelto si su estado es `corregido`. Convenciones: [README](./README.md).
"""


def parse_front_matter(text):
    """Devuelve {clave: valor} del bloque `---` inicial (YAML plano `clave: valor`, con comillas opcionales)."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    data = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            data[key.strip()] = value
    return data


def collect(docs_dir=DOCS):
    """[(carpeta, nombre_archivo, front_matter)] ordenado por ID."""
    items = []
    for kind in KINDS:
        folder = os.path.join(docs_dir, kind)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.endswith(".md"):
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    items.append((kind, name, parse_front_matter(handle.read())))
    return sorted(items, key=lambda item: item[1][:4])


def render(items):
    lines = [HEADER]
    for kind, (title, _states) in KINDS.items():
        rows = [item for item in items if item[0] == kind]
        lines.append(f"\n## {title}\n")
        if not rows:
            lines.append("_Sin documentos._")
            continue
        lines.append("| ID | Título | Estado | Resumen |\n| :--- | :--- | :--- | :--- |")
        for _kind, name, meta in rows:
            summary = meta.get("summary", "").replace("|", "\\|")
            lines.append(f"| {name[:4]} | [{meta.get('title', name)}]({kind}/{name}) | {meta.get('status', '?')} | {summary} |")
    return "\n".join(lines) + "\n"


def main(argv):
    text = render(collect())
    if "--check" in argv:
        current = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
        if current != text:
            sys.stderr.write("docs/INDEX.md no está al día: ejecuta scripts/docs_index.py\n")
            return 1
        return 0
    with open(INDEX, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"docs/INDEX.md: {len(collect())} documentos")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
