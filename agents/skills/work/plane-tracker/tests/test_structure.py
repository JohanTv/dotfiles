"""Salvaguardas estructurales del código: nombres globales no definidos, tamaño de archivos y funciones, y nombres
de módulo que sombrearían la biblioteca estándar (el directorio de scripts va primero en sys.path)."""
import ast
import builtins
import os
import symtable
import sys
import unittest

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL, "scripts")
PACKAGE = os.path.join(SCRIPTS, "plane_cli")
MAX_FILE_LINES = 450
MAX_FUNCTION_LINES = 150
MAX_MAIN_SCRIPT_LINES = 20  # plane.py es solo un shim de arranque


def sources(include_scripts=True):
    paths = []
    if include_scripts:
        paths += [os.path.join(SCRIPTS, n) for n in sorted(os.listdir(SCRIPTS)) if n.endswith(".py")]
    if os.path.isdir(PACKAGE):
        paths += [os.path.join(PACKAGE, n) for n in sorted(os.listdir(PACKAGE)) if n.endswith(".py")]
    return paths


def undefined_globals(path):
    """Nombres globales usados dentro de funciones/clases que el módulo no define ni son builtins."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    top = symtable.symtable(text, path, "exec")
    defined = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    bad = set()

    def walk(table):
        for sym in table.get_symbols():
            name = sym.get_name()
            if sym.is_global() and sym.is_referenced() and name not in defined and not hasattr(builtins, name) and name != "__file__":
                bad.add((table.get_name(), name))
        for child in table.get_children():
            walk(child)

    walk(top)
    return sorted(bad)


class Structure(unittest.TestCase):
    def test_no_undefined_global_names(self):
        for path in sources():
            self.assertEqual(undefined_globals(path), [], os.path.relpath(path, SKILL))

    def test_file_size_ratchet(self):
        for path in sources(include_scripts=False):
            with open(path, encoding="utf-8") as handle:
                lines = len(handle.read().splitlines())
            self.assertLessEqual(lines, MAX_FILE_LINES, f"{os.path.relpath(path, SKILL)} tiene {lines} líneas")
        with open(os.path.join(SCRIPTS, "plane.py"), encoding="utf-8") as handle:
            self.assertLessEqual(len(handle.read().splitlines()), MAX_MAIN_SCRIPT_LINES)

    def test_function_size(self):
        for path in sources(include_scripts=False):
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno - node.lineno + 1 > MAX_FUNCTION_LINES:
                    if node.name not in ("init_db", "cmd_comment"):  # heredadas: DDL contiguo / flujo secuencial largo
                        self.fail(f"{os.path.relpath(path, SKILL)}:{node.name} excede {MAX_FUNCTION_LINES} líneas")

    def test_module_names_do_not_shadow_stdlib(self):
        for path in sources():
            name = os.path.splitext(os.path.basename(path))[0]
            if name != "__init__":
                self.assertNotIn(name, sys.stdlib_module_names, f"{name}.py sombrea un módulo de la biblioteca estándar")

    def test_import_graph_is_acyclic_and_layered(self):
        graph = package_imports()
        self.assertTrue(graph, "no se encontró el paquete plane_cli")
        visiting, done = [], set()

        def visit(node):
            if node in done:
                return
            self.assertNotIn(node, visiting, f"ciclo de imports: {' -> '.join(visiting + [node])}")
            visiting.append(node)
            for dep in graph[node]:
                visit(dep)
            visiting.pop()
            done.add(node)

        for name in graph:
            visit(name)
        for name, deps in graph.items():
            for dep in deps:
                if not name.startswith("cmd_") and name != "cli":
                    self.assertFalse(dep.startswith("cmd_") or dep == "cli", f"la librería {name} importa {dep}")
                if name.startswith("cmd_"):
                    self.assertFalse(dep.startswith("cmd_") or dep == "cli", f"{name} importa {dep}")


def package_imports():
    """{módulo: {módulos de plane_cli que importa}} a partir del AST."""
    names = {os.path.splitext(n)[0] for n in os.listdir(PACKAGE) if n.endswith(".py")} if os.path.isdir(PACKAGE) else set()
    graph = {}
    for name in sorted(names - {"__init__"}):
        with open(os.path.join(PACKAGE, name + ".py"), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "plane_cli":
                deps |= {a.name for a in node.names if a.name in names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("plane_cli."):
                deps.add(node.module.split(".")[1])
            elif isinstance(node, ast.Import):
                deps |= {a.name.split(".")[1] for a in node.names if a.name.startswith("plane_cli.")}
        graph[name] = deps
    return graph


if __name__ == "__main__":
    unittest.main()
