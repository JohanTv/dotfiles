#!/usr/bin/env python3
"""
Diagnostic script for validating naming candidates across:
- PyPI (Python Package Index)
- crates.io (Rust Package Registry)
- npm (Node Package Registry)
- GitHub (via gh CLI search/repo API)
- Unix command / alias collisions (PATH inspection)
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = "AntigravityNamingValidator/1.0 (contact: johantv)"

CANDIDATES = [
    # (Name, Suggested Alias, Conceptual Universe, Brief Description)
    # Universe A: Astrophysics / Celestial Mechanics
    ("azimuth", "azi", "Astrofísica", "Rumbo horizontal verdadero de navegación celeste"),
    ("barycenter", "bar", "Astrofísica", "Centro de gravedad común de cuerpos orbitales en equilibrio"),
    ("perihelion", "peri", "Astrofísica", "Punto orbital de máxima velocidad y cercanía al foco gravitatorio"),
    ("periastron", "peri", "Astrofísica", "Punto orbital más cercano en sistemas estelares binarios"),
    ("periapsis", "peri", "Astrofísica", "Punto orbital de máximo impulso cinético y mínima distancia"),
    ("apsis", "aps", "Astrofísica", "Punto extremo de equilibrio orbital (perihelio o afelio)"),
    ("sidereal", "sid", "Astrofísica", "Tiempo inercial medido respecto a estrellas lejanas, verdad sin sesgo solar"),
    ("apastron", "apa", "Astrofísica", "Punto de máxima perspectiva y separación en órbita estelar"),
    ("syzygy", "syz", "Astrofísica", "Alineación gravitacional armónica de tres cuerpos en un sistema"),

    # Universe B: Biology / Homeostasis / Living Systems
    ("allostasis", "allo", "Biología", "Estabilidad adaptativa mediante cambio fisiológico activo ante el estrés"),
    ("stroma", "stro", "Biología", "Matriz estructural y de soporte que sostiene la función vital de un órgano"),
    ("turgor", "tur", "Biología", "Presión hidrostática interna que mantiene erguida y resistente a la célula vegetal"),
    ("trophism", "trof", "Biología", "Crecimiento, sostenimiento y nutrición orientada a la vitalidad sistémica"),
    ("syntropy", "synt", "Biología", "Tendencia natural a la organización, vida y disminución de entropía"),
    ("syntropia", "syn", "Biología", "Fuerza ordenadora anti-entrópica de conservación de energía y estructura"),

    # Universe C: Graph Theory / Topology / Complex Networks
    ("geodesic", "geo", "Topología", "Trayectoria más corta y eficiente en espacios curvos o grafos"),
    ("chordal", "chd", "Grafos", "Grafo triangulado donde todo ciclo tiene una cuerda; algoritmos de tiempo lineal"),
    ("plexus", "plx", "Topología", "Red intrincada y entrelazada de conexiones neuronales que operan en armonía"),
    ("conexo", "cnx", "Grafos", "Espacio topológico o red íntegramente comunicada, sin particiones disjuntas"),
    ("syndetic", "synd", "Grafos", "Enlace conectivo estructurado que vincula componentes dispersos"),
    ("holon", "hln", "Sistemas", "Entidad simultáneamente autónoma en sí misma y parte integrada de un todo"),
    ("planar", "pln", "Grafos", "Grafo proyectable sin cruce de aristas (cero fricción de merge o interferencia)"),
    ("isomorph", "iso", "Grafos", "Correspondencia exacta uno a uno que preserva estructura en distintos dominios"),

    # Universe D: Cybernetics / Systems Theory / Philosophy
    ("kairos", "kai", "Filosofía", "El momento oportuno, cualitativo y supremo de acción lúcida frente al tiempo cronológico"),
    ("ataraxia", "atx", "Filosofía", "Estado mental de serenidad imperturbable y claridad frente al caos exterior"),
    ("entelechy", "ent", "Filosofía", "Fuerza directriz interna que lleva la potencia latente a su realización plena"),
    ("praxis", "prx", "Filosofía", "Acción transformadora informada que convierte la teoría abstracta en realidad viva"),
    ("autopoiesis", "poi", "Cibernética", "Capacidad autopoiética de un sistema de regenerar y sostener su propia estructura"),
    ("homeostat", "mst", "Cibernética", "Primer dispositivo cibernético (Ashby) de autorregulación y equilibrio dinámico"),
    ("noesis", "noe", "Filosofía", "Aprehensión directa, visión intelectual y comprensión pura sin distorsión"),
]


def check_pypi(name: str):
    url = f"https://pypi.org/pypi/{name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                info = data.get("info", {})
                summary = info.get("summary", "")[:60]
                version = info.get("version", "")
                return {"status": "TAKEN", "version": version, "summary": summary}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "FREE"}
        return {"status": f"HTTP_{e.code}"}
    except Exception as e:
        return {"status": f"ERR: {e}"}


def check_crates(name: str):
    url = f"https://crates.io/api/v1/crates/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                crate = data.get("crate", {})
                downloads = crate.get("downloads", 0)
                description = (crate.get("description") or "")[:60]
                return {"status": "TAKEN", "downloads": downloads, "description": description}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "FREE"}
        return {"status": f"HTTP_{e.code}"}
    except Exception as e:
        return {"status": f"ERR: {e}"}


def check_npm(name: str):
    url = f"https://registry.npmjs.org/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                desc = data.get("description", "")[:60]
                return {"status": "TAKEN", "description": desc}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "FREE"}
        return {"status": f"HTTP_{e.code}"}
    except Exception as e:
        return {"status": f"ERR: {e}"}


def check_unix(alias: str):
    # Check if in PATH
    path_hit = shutil.which(alias)
    # Check bash builtins / type
    proc = subprocess.run(
        ["bash", "-c", f"type -t {alias} 2>/dev/null"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    btype = proc.stdout.strip()
    if path_hit or btype:
        return {"collision": True, "details": f"{btype or 'binary'} ({path_hit})"}
    return {"collision": False, "details": "CLEAN"}


def check_github(name: str):
    try:
        cmd = ["gh", "search", "repos", name, "--limit", "3", "--json", "fullName,stargazersCount,description"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode == 0:
            repos = json.loads(res.stdout)
            if not repos:
                return {"top_stars": 0, "relevance": "NONE"}
            top = repos[0]
            stars = top.get("stargazersCount", 0)
            repo_name = top.get("fullName", "")
            desc = (top.get("description") or "")[:50]
            # check exact name collision
            exact_hits = [r for r in repos if r.get("fullName", "").lower().endswith(f"/{name.lower()}")]
            return {
                "top_stars": stars,
                "top_repo": repo_name,
                "top_desc": desc,
                "exact_hits": len(exact_hits),
            }
        else:
            return {"top_stars": -1, "error": res.stderr.strip()[:40]}
    except Exception as e:
        return {"top_stars": -1, "error": str(e)[:40]}


def main():
    print(f"=== Validando {len(CANDIDATES)} candidatos en tiempo real ===\n")
    results = []

    for name, alias, universe, desc in CANDIDATES:
        sys.stdout.write(f"Verificando '{name}' ({alias})... ")
        sys.stdout.flush()

        pypi = check_pypi(name)
        time.sleep(0.1)
        crates = check_crates(name)
        time.sleep(0.1)
        npm = check_npm(name)
        time.sleep(0.1)
        unix = check_unix(alias)
        gh = check_github(name)

        item = {
            "name": name,
            "alias": alias,
            "universe": universe,
            "concept": desc,
            "pypi": pypi,
            "crates": crates,
            "npm": npm,
            "unix": unix,
            "github": gh,
        }
        results.append(item)

        pypi_str = "FREE" if pypi.get("status") == "FREE" else "TAKEN"
        crates_str = "FREE" if crates.get("status") == "FREE" else "TAKEN"
        npm_str = "FREE" if npm.get("status") == "FREE" else "TAKEN"
        unix_str = "OK" if not unix.get("collision") else "COLLISION!"
        gh_stars = gh.get("top_stars", 0)

        print(f"PyPI: {pypi_str} | Crates: {crates_str} | NPM: {npm_str} | Unix: {unix_str} | GH Stars: {gh_stars}")

    output_path = "/home/johantv/Code/dotfiles/docs/scratch/results_raw.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResultados guardados en {output_path}")


if __name__ == "__main__":
    main()
