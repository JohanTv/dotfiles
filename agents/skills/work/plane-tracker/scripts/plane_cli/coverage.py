"""Cobertura de una lectura (de dónde salen los datos y si están completos), el resultado que la lleva y las notas que se derivan de ella.

Expone: Coverage (con merge() y to_dict()), Result, combine(), complete_list(), complete_time(), complete_flow(), complete_agenda(),
complete_get(), completeness_label(), notes_from(), build_notes().
No hace: leer SQLite, tocar la red ni imprimir. `complete` tiene tres valores: True, False y None (no verificado, nunca equivale a completo).
`complete` describe la cobertura de la FUENTE (la caché frente al servidor), no si la página muestra todo: eso lo dicen `total`, `count` y la nota `truncated`.
Las notas no se escriben a mano: se derivan de la cobertura, del resultado y del alcance (una sola fuente por hecho); la consulta solo
aporta las propias de su vista (Result.extra_notes), que deben estar registradas con origen `vista`.
Los hechos de coverage.detail que alimentan notas y la regla de `complete`: forbidden, capped, count_mismatch (listas de proyectos), legacy,
rate_budget_exhausted, assignment_snapshot (bool), history {verified, total}, hours_scope ("local" o "synced") y hours_verified (True/False/None).
"""

from dataclasses import dataclass, field

from plane_cli import vocabulary
from plane_cli.timeutil import age_text


def combine(*values):
    """False si alguna parte lo es, None si alguna es desconocida, True solo si todas lo son."""
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True


@dataclass(frozen=True)
class Coverage:
    source: str
    as_of: str | None = None
    age_s: int | None = None
    stale: bool = False
    complete: bool | None = None
    unavailable: tuple = ()
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.source not in vocabulary.COVERAGE_SOURCES:
            raise ValueError(f"origen de cobertura no válido: {self.source}")
        if self.complete not in (True, False, None) or not isinstance(self.complete, (bool, type(None))):
            raise ValueError(f"complete debe ser True, False o None: {self.complete!r}")
        object.__setattr__(self, "unavailable", tuple(self.unavailable))
        object.__setattr__(self, "detail", dict(self.detail))

    def to_dict(self):
        return {"source": self.source, "as_of": self.as_of, "age_s": self.age_s, "stale": self.stale, "complete": self.complete,
                "unavailable": list(self.unavailable), "detail": dict(self.detail)}

    @staticmethod
    def merge(*parts):
        """as_of el más antiguo, source `mixed` si difieren, complete por `combine`, detail unido (history se suma)."""
        if not parts:
            raise ValueError("merge necesita al menos una cobertura")
        sources = {p.source for p in parts}
        as_ofs, ages = [p.as_of for p in parts if p.as_of], [p.age_s for p in parts if p.age_s is not None]
        detail = {}
        for part in parts:
            for key, value in part.detail.items():
                if key == "history" and key in detail:
                    value = {k: detail[key][k] + value[k] for k in ("verified", "total")}
                detail[key] = value
        return Coverage(source=sources.pop() if len(sources) == 1 else "mixed", as_of=min(as_ofs) if as_ofs else None,
                        age_s=max(ages) if ages else None, stale=any(p.stale for p in parts),
                        complete=combine(*(p.complete for p in parts)),
                        unavailable=tuple(sorted({u for p in parts for u in p.unavailable})), detail=detail)


@dataclass(frozen=True)
class Result:
    """Resultado de una consulta: filas, total antes del límite, agregados y cobertura (obligatoria: no existe un Result sin ella)."""
    rows: tuple
    total: int
    coverage: Coverage
    summary: dict | None = None
    extra_notes: tuple = ()

    def __post_init__(self):
        if not isinstance(self.coverage, Coverage):
            raise TypeError("un Result necesita su Coverage")
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "extra_notes", tuple(self.extra_notes))
        if self.total < len(self.rows):
            raise ValueError(f"total ({self.total}) no puede ser menor que las filas ({len(self.rows)})")


def completeness_label(complete):
    """Cómo se muestra `complete` en el texto: None nunca se muestra como completo."""
    return {True: "completa", False: "incompleta"}.get(complete, "no verificada")


# --- Regla de `complete` por vista (modelo de consulta, tabla "Regla de complete") ------------------------------------------------------
def _generic(cov):
    """Lo que impide el True en cualquier vista: falta algo conocido (False) o hay algo sin verificar (None)."""
    d = cov.detail
    if cov.unavailable or any(d.get(k) for k in ("forbidden", "capped", "rate_budget_exhausted", "count_mismatch")):
        return False
    history = d.get("history")
    if cov.stale or d.get("legacy") or d.get("hours_scope") == "local" or (history and history["verified"] < history["total"]):
        return None
    return True


def complete_list(cov):
    """True si los tickets en caché son todos los del servidor (count_mismatch vacío) dentro del TTL, sin legacy ni capped."""
    return _generic(cov)


def complete_time(cov):
    """True si la sincronización de horas está verificada para cada proyecto y todo el periodo (detail.hours_verified); sin dato, None."""
    return combine(_generic(cov), cov.detail.get("hours_verified"))


def complete_flow(cov):
    """True si todos los tickets del alcance tienen transiciones al día (detail.history); False si faltan; None si no se informó."""
    history = cov.detail.get("history")
    own = None if history is None else history["verified"] >= history["total"]
    return combine(_generic(cov), own)


def complete_agenda(list_cov, time_cov):
    return combine(complete_list(list_cov), complete_time(time_cov))


def complete_get(cov, comments_read):
    """True solo si el ticket vino de la API y sus comentarios se leyeron completos; con instantánea o sin leerlos, None."""
    if cov.source != "api" or comments_read is not True:
        return None
    return _generic(cov)


# --- Notas derivadas ---------------------------------------------------------------------------------------------------------------------
def _note(code, **facts):
    severity, _origin, template, hint = vocabulary.NOTES[code]
    note = {"code": code, "text": template.format(**facts)}
    if hint:
        note["hint"] = hint
    return note


def notes_from(cov, scope, result):
    """Notas implicadas por la cobertura, el resultado y el alcance (dict ya resuelto o None). Sin ordenar ni filtrar por severidad."""
    d, notes = cov.detail, []
    names = lambda items: ", ".join(sorted(items))
    if cov.stale:
        notes.append(_note("cache_stale", age=age_text(cov.age_s) if cov.age_s is not None else "?"))
    for code, items in (("source_unavailable", cov.unavailable), ("source_forbidden", d.get("forbidden")), ("cache_capped", d.get("capped"))):
        if items:
            notes.append(_note(code, projects=names(items)))
    for code, fact in (("rate_budget_exhausted", d.get("rate_budget_exhausted")), ("legacy_cache", d.get("legacy")),
                       ("assignment_snapshot", d.get("assignment_snapshot")), ("hours_local_only", d.get("hours_scope") == "local")):
        if fact:
            notes.append(_note(code))
    history = d.get("history")
    if history and history["verified"] < history["total"]:
        notes.append(_note("history_partial", verified=history["verified"], total=history["total"]))
    if result is not None and result.total > len(result.rows):
        notes.append(_note("truncated", count=len(result.rows), total=result.total))
    projects = (scope or {}).get("projects") or []
    if len(projects) == 1:
        notes.append(_note("single_project", project=projects[0]))
    return notes


def build_notes(cov, scope, result, verbose=False):
    """Notas derivadas más las propias de la vista, validadas contra el registro; informativas solo con verbose; avisos primero, luego por código."""
    notes = notes_from(cov, scope, result)
    for extra in result.extra_notes:
        code = extra.get("code")
        entry = vocabulary.NOTES.get(code)
        if entry is None or entry[1] != "vista":
            raise ValueError(f"extra_notes solo admite códigos registrados con origen `vista`: {code}")
        note = {"code": code, "text": extra["text"]}
        if extra.get("hint") or entry[3]:
            note["hint"] = extra.get("hint") or entry[3]
        notes.append(note)
    if not verbose:
        notes = [n for n in notes if vocabulary.NOTES[n["code"]][0] == "warn" or n["code"] in vocabulary.ALWAYS_SHOWN]
    return sorted(notes, key=lambda n: (vocabulary.SEVERITY_ORDER.index(vocabulary.NOTES[n["code"]][0]), n["code"]))
