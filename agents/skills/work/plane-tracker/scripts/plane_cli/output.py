"""Salida de las vistas de lectura: el sobre serializado en `--json` o su render en texto.

Expone: emit().
No hace: consultar ni construir el sobre. Lo que va en `notes` y `coverage` no se repite por stderr.
"""

from plane_cli.envelope import dumps


def emit(view, doc, as_json=False, **render_options):
    print(dumps(doc) if as_json else view.render(doc, **render_options), end="" if not as_json else "\n")
