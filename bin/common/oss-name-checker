#!/usr/bin/env python3
"""
OSS Name Checker: Sovereign Real-Time Registry & Namespace Availability Validator.

Queries public APIs in real time to verify namespace availability across:
- PyPI (Python Package Index)
- crates.io (Rust Package Registry)
- npm (Node Package Registry)
- GitHub (Repositories & community footprint via `gh` CLI or public API)
- Unix Terminal Environment (Collision with standard Linux binaries, builtins, and shell functions)

Zero heavy third-party dependencies: runs on pure Python 3.8+ standard library.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = "OSS-Name-Checker/1.0 (+https://github.com/johantv/oss-name-checker)"

# ANSI terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


class NameValidator:
    def __init__(self, timeout: float = 5.0, user_agent: str = USER_AGENT):
        self.timeout = timeout
        self.user_agent = user_agent

    def check_pypi(self, name: str) -> Dict[str, Any]:
        url = f"https://pypi.org/pypi/{name}/json"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    info = data.get("info", {})
                    return {
                        "available": False,
                        "status": "TAKEN",
                        "version": info.get("version", ""),
                        "summary": (info.get("summary") or "")[:80],
                        "url": info.get("project_url") or f"https://pypi.org/project/{name}/",
                    }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"available": True, "status": "FREE", "details": "404 Not Found"}
            return {"available": False, "status": f"HTTP_{e.code}", "details": e.reason}
        except Exception as ex:
            return {"available": False, "status": "ERROR", "details": str(ex)}
        return {"available": False, "status": "UNKNOWN"}

    def check_crates(self, name: str) -> Dict[str, Any]:
        url = f"https://crates.io/api/v1/crates/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    crate = data.get("crate", {})
                    return {
                        "available": False,
                        "status": "TAKEN",
                        "downloads": crate.get("downloads", 0),
                        "description": (crate.get("description") or "")[:80],
                        "url": f"https://crates.io/crates/{name}",
                    }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"available": True, "status": "FREE", "details": "404 Not Found"}
            return {"available": False, "status": f"HTTP_{e.code}", "details": e.reason}
        except Exception as ex:
            return {"available": False, "status": "ERROR", "details": str(ex)}
        return {"available": False, "status": "UNKNOWN"}

    def check_npm(self, name: str) -> Dict[str, Any]:
        url = f"https://registry.npmjs.org/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    desc = (data.get("description") or "")[:80]
                    return {
                        "available": False,
                        "status": "TAKEN",
                        "description": desc,
                        "url": f"https://www.npmjs.com/package/{name}",
                    }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"available": True, "status": "FREE", "details": "404 Not Found"}
            return {"available": False, "status": f"HTTP_{e.code}", "details": e.reason}
        except Exception as ex:
            return {"available": False, "status": "ERROR", "details": str(ex)}
        return {"available": False, "status": "UNKNOWN"}

    def check_unix(self, cmd: str) -> Dict[str, Any]:
        path_binary = shutil.which(cmd)
        proc = subprocess.run(
            ["bash", "-c", f"type -t {cmd} 2>/dev/null"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        builtin_type = proc.stdout.strip()
        collision = bool(path_binary or builtin_type)
        return {
            "collision": collision,
            "status": "COLLISION" if collision else "FREE",
            "path": path_binary or "",
            "type": builtin_type or "",
        }

    def check_github(self, name: str) -> Dict[str, Any]:
        # Priority 1: gh CLI if installed and working
        if shutil.which("gh"):
            try:
                cmd = ["gh", "search", "repos", name, "--limit", "3", "--json", "fullName,stargazersCount,description,url"]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=self.timeout + 3)
                if res.returncode == 0:
                    repos = json.loads(res.stdout)
                    if not repos:
                        return {"top_stars": 0, "status": "FREE", "repos": []}
                    top = repos[0]
                    stars = top.get("stargazersCount", 0)
                    exact = [r for r in repos if r.get("fullName", "").lower().endswith(f"/{name.lower()}")]
                    return {
                        "status": "OCCUPIED" if (stars > 50 or exact) else "LOW_FOOTPRINT",
                        "top_stars": stars,
                        "top_repo": top.get("fullName", ""),
                        "top_desc": (top.get("description") or "")[:80],
                        "exact_matches": len(exact),
                        "repos": repos,
                    }
            except Exception:
                pass

        # Fallback 2: public API
        url = f"https://api.github.com/search/repositories?q={name}+in:name&sort=stars&order=desc&per_page=3"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/vnd.github.v3+json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    items = data.get("items", [])
                    if not items:
                        return {"top_stars": 0, "status": "FREE", "repos": []}
                    top = items[0]
                    stars = top.get("stargazers_count", 0)
                    exact = [r for r in items if r.get("name", "").lower() == name.lower()]
                    return {
                        "status": "OCCUPIED" if (stars > 50 or exact) else "LOW_FOOTPRINT",
                        "top_stars": stars,
                        "top_repo": top.get("full_name", ""),
                        "top_desc": (top.get("description") or "")[:80],
                        "exact_matches": len(exact),
                    }
        except Exception as ex:
            return {"status": "UNCHECKED", "error": str(ex)}

        return {"status": "UNCHECKED"}

    def validate_candidate(self, name: str, alias: Optional[str] = None) -> Dict[str, Any]:
        target_alias = alias or name[:4].lower()
        pypi_res = self.check_pypi(name)
        crates_res = self.check_crates(name)
        npm_res = self.check_npm(name)
        unix_alias_res = self.check_unix(target_alias)
        unix_name_res = self.check_unix(name)
        gh_res = self.check_github(name)

        # Risk score calculation (0 = completely pristine, 100 = saturated)
        score = 0
        if not pypi_res.get("available"):
            score += 30
        if not crates_res.get("available"):
            score += 25
        if not npm_res.get("available"):
            score += 25
        if gh_res.get("status") == "OCCUPIED":
            stars = gh_res.get("top_stars", 0)
            if stars > 1000:
                score += 35
            elif stars > 100:
                score += 20
            else:
                score += 10
        if unix_alias_res.get("collision"):
            score += 15

        viability = "EXCELLENT" if score == 0 else ("GOOD" if score <= 20 else ("MODERATE" if score <= 50 else "DISCARDED"))

        return {
            "name": name,
            "alias": target_alias,
            "viability": viability,
            "risk_score": score,
            "pypi": pypi_res,
            "crates": crates_res,
            "npm": npm_res,
            "unix_alias": unix_alias_res,
            "unix_name": unix_name_res,
            "github": gh_res,
        }


def format_cli_table(results: List[Dict[str, Any]], use_color: bool = True) -> str:
    lines = []
    header = f"{'Nombre':<15} {'Alias':<7} {'PyPI':<8} {'Crates':<8} {'NPM':<8} {'Unix':<8} {'GH Stars':<10} {'Viabilidad':<10}"
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        name = r["name"]
        alias = r["alias"]
        p = "FREE" if r["pypi"].get("available") else "TAKEN"
        c = "FREE" if r["crates"].get("available") else "TAKEN"
        n = "FREE" if r["npm"].get("available") else "TAKEN"
        u = "COLLISION" if r["unix_alias"].get("collision") else "OK"
        stars = str(r["github"].get("top_stars", 0))
        viab = r["viability"]

        if use_color and sys.stdout.isatty():
            p_str = f"{GREEN}FREE{RESET}" if p == "FREE" else f"{RED}TAKEN{RESET}"
            c_str = f"{GREEN}FREE{RESET}" if c == "FREE" else f"{RED}TAKEN{RESET}"
            n_str = f"{GREEN}FREE{RESET}" if n == "FREE" else f"{RED}TAKEN{RESET}"
            u_str = f"{GREEN}OK{RESET}" if u == "OK" else f"{RED}COLLISION{RESET}"
            v_color = GREEN if viab == "EXCELLENT" else (YELLOW if viab in ("GOOD", "MODERATE") else RED)
            viab_str = f"{v_color}{viab}{RESET}"
            lines.append(f"{BOLD}{name:<15}{RESET} {alias:<7} {p_str:<17} {c_str:<17} {n_str:<17} {u_str:<17} {stars:<10} {viab_str}")
        else:
            lines.append(f"{name:<15} {alias:<7} {p:<8} {c:<8} {n:<8} {u:<8} {stars:<10} {viab:<10}")

    return "\n".join(lines)


def format_markdown_table(results: List[Dict[str, Any]]) -> str:
    lines = [
        "| Candidato | Alias | PyPI | Crates.io | npm | Unix Alias | GitHub Top Stars | Viabilidad |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in results:
        name = f"`{r['name']}`"
        alias = f"`{r['alias']}`"
        p = "✅ Libre" if r["pypi"].get("available") else "❌ Ocupado"
        c = "✅ Libre" if r["crates"].get("available") else "❌ Ocupado"
        n = "✅ Libre" if r["npm"].get("available") else "❌ Ocupado"
        u = "⚠️ Colisión" if r["unix_alias"].get("collision") else "✅ Libre"
        stars = r["github"].get("top_stars", 0)
        gh_str = f"{stars} ⭐" if stars > 0 else "0 ⭐ (Prístino)"
        viab = r["viability"]
        viab_badge = {
            "EXCELLENT": "🟢 Excelente (Prístino)",
            "GOOD": "🟡 Bueno (Mínimo riesgo)",
            "MODERATE": "🟠 Moderado",
            "DISCARDED": "🔴 Descartado",
        }.get(viab, viab)

        lines.append(f"| {name} | {alias} | {p} | {c} | {n} | {u} | {gh_str} | {viab_badge} |")

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(
        description="OSS Name Checker: Sovereign namespace and registry availability validator."
    )
    parser.add_argument("names", nargs="*", help="One or more project candidate names to inspect.")
    parser.add_argument("--alias", "-a", help="Suggested CLI alias for single-name checks.")
    parser.add_argument("--file", "-f", help="Text file with candidate names (one per line, optionally 'name:alias').")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    parser.add_argument("--markdown", "-m", action="store_true", help="Output results formatted as a Markdown table.")
    parser.add_argument("--timeout", "-t", type=float, default=5.0, help="HTTP request timeout in seconds (default: 5.0).")
    parser.add_argument("--output", "-o", help="Save output directly to a file.")
    return parser.parse_args()


def main():
    args = parse_args()
    candidates: List[Tuple[str, Optional[str]]] = []

    if args.names:
        if len(args.names) == 1 and args.alias:
            candidates.append((args.names[0], args.alias))
        else:
            for item in args.names:
                if ":" in item:
                    n, a = item.split(":", 1)
                    candidates.append((n.strip(), a.strip()))
                else:
                    candidates.append((item.strip(), None))

    if args.file:
        if not os.path.exists(args.file):
            sys.stderr.write(f"Error: File not found: {args.file}\n")
            sys.exit(1)
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    n, a = line.split(":", 1)
                    candidates.append((n.strip(), a.strip()))
                elif " " in line:
                    parts = line.split()
                    candidates.append((parts[0].strip(), parts[1].strip() if len(parts) > 1 else None))
                else:
                    candidates.append((line, None))

    if not candidates:
        parser = argparse.ArgumentParser()
        sys.stderr.write("Error: No candidate names provided. Use positional arguments or --file.\n")
        sys.stderr.write("Example: python3 name_checker.py allostasis --alias allo\n")
        sys.exit(1)

    validator = NameValidator(timeout=args.timeout)
    results = []

    for name, alias in candidates:
        if not args.json and not args.markdown:
            sys.stderr.write(f"Checking {name}...")
            sys.stderr.flush()
        res = validator.validate_candidate(name, alias)
        results.append(res)
        if not args.json and not args.markdown:
            sys.stderr.write("\r" + " " * 30 + "\r")
        time.sleep(0.15)  # respectful delay between queries

    if args.json:
        output_str = json.dumps(results, indent=2, ensure_ascii=False)
    elif args.markdown:
        output_str = format_markdown_table(results)
    else:
        output_str = format_cli_table(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str + "\n")
        print(f"Results written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
