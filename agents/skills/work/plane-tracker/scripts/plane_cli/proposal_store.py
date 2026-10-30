"""Almacén de propuestas de duración (last_proposal.json) con exclusión entre procesos y vigencia.

Expone: save_proposal(), save_group(), load_recent_proposal(), consume_proposal(), proposal_store(), PROPOSAL_TTL_SECONDS.
No hace: medir sesiones ni calcular propuestas.
"""

import contextlib
import fcntl
import json
import os
import time

from plane_cli import config


PROPOSAL_TTL_SECONDS = 30 * 60


@contextlib.contextmanager
def proposal_store():
    """last_proposal.json con lectura-modificación-escritura atómica y exclusión entre procesos."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    proposal_path = config.proposal_file()
    with open(proposal_path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(proposal_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        if not isinstance(data.get("proposals"), dict) or not isinstance(data.get("groups"), dict):
            data = {"proposals": {}, "groups": {}}
        cutoff = time.time() - PROPOSAL_TTL_SECONDS
        data["proposals"] = {k: v for k, v in data["proposals"].items() if v.get("ts", 0) > cutoff}
        data["groups"] = {k: v for k, v in data["groups"].items() if v.get("ts", 0) > cutoff}
        yield data
        tmp = proposal_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, proposal_path)


def _entry_key(ticket, session_id):
    return f"{ticket}|{session_id}"


def _drop_ticket(data, tickets, session_id):
    """Quita las propuestas pendientes de esos tickets SOLO en esa sesión (otras sesiones no se tocan)."""
    for t in tickets:
        data["proposals"].pop(_entry_key(t, session_id), None)
    for gid in list(data["groups"]):
        group = data["groups"][gid]
        if group.get("session") != session_id:
            continue
        for t in tickets:
            group["parts"].pop(t, None)
        if not group["parts"]:
            del data["groups"][gid]


def save_proposal(ticket, proposal):
    with proposal_store() as data:
        _drop_ticket(data, [ticket], proposal["session_id"])
        data["proposals"][_entry_key(ticket, proposal["session_id"])] = {"ts": time.time(), "ticket": ticket, "proposal": proposal}


def save_group(group_id, parts):
    """parts: {ticket: propuesta} de una misma sesión; reemplaza lo pendiente de esos tickets en ella."""
    session_id = next(iter(parts.values()))["session_id"]
    with proposal_store() as data:
        _drop_ticket(data, list(parts), session_id)
        data["groups"][group_id] = {"ts": time.time(), "session": session_id, "parts": parts}


def load_recent_proposal(ticket, session_id=None):
    """La propuesta vigente del ticket (suelta o parte de un reparto) de esa sesión, la más reciente.

    Sin `session_id` solo se devuelve si hay una única sesión con propuesta para el ticket: con varias
    terminales abiertas no se adivina cuál es la tuya.
    """
    with proposal_store() as data:
        found = []
        for entry in data["proposals"].values():
            if entry.get("ticket") == ticket:
                found.append((entry["ts"], entry["proposal"]))
        for group in data["groups"].values():
            if ticket in group["parts"]:
                found.append((group["ts"], group["parts"][ticket]))
    if session_id:
        found = [f for f in found if f[1].get("session_id") == session_id]
    elif len({f[1].get("session_id") for f in found}) > 1:
        return None
    return max(found, key=lambda x: x[0])[1] if found else None


def consume_proposal(ticket, session_id):
    """Una propuesta aceptada no puede volver a usarse (evita registrar dos veces lo mismo)."""
    with proposal_store() as data:
        _drop_ticket(data, [ticket], session_id)
