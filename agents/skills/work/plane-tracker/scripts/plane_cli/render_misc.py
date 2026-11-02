"""Texto de las vistas simples `whoami`, `attachment list` y `outbox list`, a partir del sobre.

Expone: render_whoami(), render_attachments(), render_outbox().
No hace: consultar, leer el entorno ni el reloj.
"""

from datetime import datetime


def render_whoami(doc):
    row = doc["results"][0]
    lines = [f"🌐 PLANE_BASE_URL  : {row.get('base_url') or ''}", f"🏢 PLANE_WORKSPACE : {row['workspace']}"]
    if row["source"] == "actor_env":
        lines.append(f"🔑 PLANE_ACTOR_UUID: {row['actor']} (configurado directamente)")
    elif row["source"] == "username":
        lines.append(f"👤 PLANE_USERNAME  : {row['username']} (resolviendo UUID...)")
        if row["status"] == "ok":
            lines += [f"✅ UUID resuelto   : {row['actor']}", "\n💡 Tip: para acelerar futuros syncs, agrega a ~/.zshrc.local:", f"   export PLANE_ACTOR_UUID=\"{row['actor']}\""]
        else:
            lines += [f"❌ No se pudo resolver el UUID para PLANE_USERNAME='{row['username']}'",
                      "   Verifica que el nombre o email coincida exactamente con tu perfil en Plane."]
    else:
        lines += ["⚠️  Ni PLANE_USERNAME ni PLANE_ACTOR_UUID están configurados.",
                  "   El sync funcionará pero mezclará horas de todos los autores en tickets compartidos.", "\n📋 Setup requerido en ~/.zshrc.local:",
                  "   export PLANE_USERNAME=\"tu@email.com\"  # o tu display_name en Plane", "   # Opcional (más robusto):",
                  "   export PLANE_ACTOR_UUID=\"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\""]
    if row["status"] == "ok":
        lines.append("\n✅ Configuración válida. Puedes usar plane-tracker normalmente.")
    return "\n".join(lines) + "\n"


def _stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


def render_attachments(doc):
    of = f" de {doc['results'][0]['ticket']}" if doc["results"] else ""
    lines = [f"\n📎 Adjuntos{of} ({doc['total']}):"]
    lines += [f"   • {r['name']}  ({(r['size'] or 0) / 1024:.1f} KB)  {_stamp(r['created_at'])}  {r['id']}" for r in doc["results"]]
    return "\n".join(lines) + "\n\n"


def render_outbox(doc):
    if not doc["results"]:
        return ("La cola está vacía." if doc["scope"].get("state") != "all" else "No hay registros en la cola.") + "\n"
    lines = []
    for it in doc["results"]:
        flag = " · pudo enviarse" if it["maybe_delivered"] and it["state"] != "sent" else ""
        lines.append(f"#{it['id']} [{it['state']}] {it['ticket']} · {it['track']} · {it['date']} {it['start_time']} · {it['minutes'] or '?'} min · {it['attempts']} intento(s){flag}")
        lines.append(f"   {it['preview']}")
        if it["last_error"]:
            lines.append(f"   último error: {it['last_error']}")
    return "\n".join(lines) + "\n"
