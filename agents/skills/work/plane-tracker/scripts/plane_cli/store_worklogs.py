"""Almacén de solo lectura de la sincronización de horas: qué proyectos entran en el alcance y si el periodo está verificado contra Plane.

Expone: HoursStatus, accessible_idents(), hours_status().
No hace: red ni escribir (las marcas las escribe sync.py). La verificación es por proyecto y periodo (defecto 0010): un proyecto está verificado si hay una
sincronización completa cuyo periodo cubre el pedido; nunca sincronizado o incompleto => no verificado (`verified: False`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HoursStatus:
    verified: bool | None    # True: cada proyecto con sincronización completa del periodo; False: alguno sin sincronizar o incompleto; None: no hay proyectos que mirar
    as_of: float | None      # época de la sincronización más antigua usada (None si ninguna)
    never: tuple = ()        # proyectos sin ninguna sincronización que cubra el periodo
    partial: tuple = ()      # proyectos cuya última sincronización quedó incompleta
    unmeasured: int = 0      # comentarios con telemetría sin fecha u hora, que no entraron (suma de las marcas usadas)


def accessible_idents(conn, workspace, only=None):
    """Identificadores de los proyectos accesibles (miembro y no archivado) que conoce la caché; con `only`, solo ese si es accesible."""
    rows = conn.execute("SELECT identifier FROM projects WHERE workspace = ? AND is_member = 1 AND archived = 0 ORDER BY identifier", (workspace,)).fetchall()
    idents = [r["identifier"] for r in rows]
    return [i for i in idents if i == only.upper()] if only else idents


def hours_status(conn, idents, date_from, date_to):
    """HoursStatus de `idents` para [date_from, date_to] (YYYY-MM-DD): usa, por proyecto, la sincronización más reciente que cubre todo el periodo."""
    if not idents:
        return HoursStatus(None, None)
    never, partial, as_ofs, unmeasured = [], [], [], 0
    for ident in idents:
        row = conn.execute("SELECT as_of, complete, unmeasured FROM worklog_sync WHERE project_ident = ? AND date_from <= ? AND date_to >= ? "
                           "ORDER BY as_of DESC LIMIT 1", (ident, date_from, date_to)).fetchone()
        if row is None:
            never.append(ident)
            continue
        as_ofs.append(row["as_of"])
        unmeasured += row["unmeasured"]
        if not row["complete"]:
            partial.append(ident)
    return HoursStatus(not never and not partial, min(as_ofs) if as_ofs else None, tuple(never), tuple(partial), unmeasured)


def rows(conn, idents, date_from, date_to, track=None, worker_type=None):
    """Registros de horas de la base local de los proyectos `idents` en [date_from, date_to], de cualquier autor (el filtro por autor es de la consulta), ordenados."""
    if not idents:
        return []
    sql = f"SELECT * FROM worklogs WHERE date >= ? AND date <= ? AND project_id IN ({','.join('?' for _ in idents)})"
    params = [date_from, date_to, *idents]
    for column, value in (("track", track), ("worker_type", worker_type)):
        if value:
            sql += f" AND {column} = ?"
            params.append(value)
    return conn.execute(sql + " ORDER BY date, start_time, ticket_id", params).fetchall()
