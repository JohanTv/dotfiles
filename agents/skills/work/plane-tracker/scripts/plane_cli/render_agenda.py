"""Texto de la vista `agenda`: render del sobre `plane-tracker/1`, nunca de la base de datos.

Expone: render().
No hace: consultar ni leer el entorno ni el reloj; todo lo que muestra sale del sobre.
"""

from plane_cli import vocabulary
from plane_cli.timeutil import format_minutes


def _line_brief(r):
    prio = f"[{r['priority'].upper()}]" if r.get("priority") else f"({r['state_group']})"
    tags = []
    if r.get("is_focus"):
        tags.append("EN FOCO")
    if r.get("is_stalled"):
        tags.append(f"⚠️ ESTANCADO {r['days_since_update']}d")
    if r.get("is_overdue"):
        tags.append("VENCIDO")
    if r.get("dod_total"):
        tags.append(f"DoD {r['dod_completed']}/{r['dod_total']}")
    if r.get("section") == "blocked" and r.get("blocker_reason"):
        tags.append(f"Standby {r['standby_days']}d: {r['blocker_reason'][:30]}")
    tag_str = f" ({' · '.join(tags)})" if tags else ""
    raw_title = (r.get("title") or "").splitlines()[0] if (r.get("title") or "").splitlines() else ""
    return f"  {'▶' if r.get('is_focus') else '⏸' if r.get('section') == 'blocked' else '•'} {r['ticket']:<12} {r['state']:<12} {prio:<9} {raw_title[:50]}{tag_str}"


def _render_brief(doc):
    s = doc.get("summary") or {}
    head = f"🎯 AGENDA · WIP: {s.get('wip_count', 0)}/{s.get('wip_limit', 2)} · Bloqueados: {s.get('blocked_count', 0)} · Horas sem: {format_minutes(s.get('logged_clock_minutes_week', 0))} ({s.get('ai_leverage_multiplier', 1.0)}x)"
    lines = [head]
    for r in doc.get("results") or []:
        lines.append(_line_brief(r))
    return "\n".join(lines) + "\n"


def render(doc, brief=False):
    if brief or doc.get("scope", {}).get("brief"):
        return _render_brief(doc)

    s = doc.get("summary") or {}
    wip_cnt, wip_lim = s.get("wip_count", 0), s.get("wip_limit", 2)
    wip_warn = " ⚠️ LÍMITE EXCEDIDO" if s.get("wip_exceeded") else ""
    today_str = (doc.get("coverage", {}).get("detail", {}).get("today") or "")
    lines = [
        "=" * 80,
        f"🎯 AGENDA PERSONAL · {today_str}".strip(),
        "=" * 80,
        f"🔥 EN CURSO [WIP: {wip_cnt} / máx {wip_lim}]{wip_warn}",
    ]

    active = [r for r in doc.get("results") or [] if r.get("section") in ("active_focus", "in_progress")]
    if not active:
        lines.append("  • (sin tareas en curso)")
    else:
        for r in active:
            mark = "▶" if r.get("is_focus") else "•"
            prio = f"[{r['priority'].upper()}]" if r.get("priority") else ""
            t_title = (r.get("title") or "").splitlines()[0] if (r.get("title") or "").splitlines() else ""
            lines.append(f"  {mark} {r['ticket']:<12} {prio:<9} {t_title}")
            sub = []
            if r.get("is_focus"):
                sub.append(f"En foco ({r.get('focus_source') or 'activo'})")
            if r.get("is_stalled"):
                sub.append(f"⚠️ ESTANCADO (Sin cambios hace {r['days_since_update']}d)")
            if r.get("is_overdue"):
                sub.append("VENCIDO")
            elif r.get("target_date") == today_str and today_str:
                sub.append("VENCE HOY")
            if r.get("dod_total"):
                sub.append(f"DoD: {r['dod_completed']}/{r['dod_total']}")
            fallback = f"Activo hace {r.get('days_since_update', 0)}d"
            lines.append(f"    ↳ {' · '.join(sub) if sub else fallback}")

    blocked = [r for r in doc.get("results") or [] if r.get("section") == "blocked"]
    lines.append(f"\n⏸️ BLOQUEADO / STANDBY [{len(blocked)} ticket(s)]")
    if not blocked:
        lines.append("  (sin bloqueos activos)")
    else:
        for r in blocked:
            prio = f"[{r['priority'].upper()}]" if r.get("priority") else ""
            t_title = (r.get("title") or "").splitlines()[0] if (r.get("title") or "").splitlines() else ""
            lines.append(f"  ⏸ {r['ticket']:<12} {prio:<9} {t_title}")
            reason = r.get("blocker_reason") or "En espera externa"
            lines.append(f"    ↳ Pausado hace {r['standby_days']}d · Motivo: {reason}")

    queue = [r for r in doc.get("results") or [] if r.get("section") == "pull_queue"]
    lines.append("\n📥 SIGUIENTE EN COLA (Pull Queue)")
    if not queue:
        lines.append("  (cola vacía)")
    else:
        for i, r in enumerate(queue, 1):
            prio = f"[{r['priority'].upper()}]" if r.get("priority") else ""
            t_title = (r.get("title") or "").splitlines()[0] if (r.get("title") or "").splitlines() else ""
            lines.append(f"  {i}. {r['ticket']:<12} {prio:<9} {t_title}")

    clock_m = s.get("logged_clock_minutes_week", 0)
    leverage = s.get("ai_leverage_multiplier", 1.0)
    lines += [
        f"\n📊 CAPACIDAD SEMANA: {format_minutes(clock_m)} reloj · AI Leverage: {leverage}x",
        "=" * 80,
    ]
    for n in doc.get("notes") or []:
        mark = "⚠" if vocabulary.NOTES.get(n["code"], ("warn",))[0] == "warn" else "ℹ"
        lines.append(f"  {mark} {n['text']}" + (f" → {n['hint']}" if n.get("hint") else ""))

    return "\n".join(lines) + "\n"
