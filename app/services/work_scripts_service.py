import os
import subprocess
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db import WorkScript

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
LAUNCH_SH = os.path.expanduser("~/scripts/launch.sh")


def list_scripts(db: Session) -> list:
    scripts = db.query(WorkScript).order_by(WorkScript.order).all()
    return [{"id": s.id, "name": s.name, "title": s.title, "filename": s.filename, "enabled": s.enabled, "order": s.order} for s in scripts]


def create_script(db: Session, name: str, title: str, filename: str, enabled: bool, order: int) -> dict:
    script = WorkScript(name=name, title=title, filename=filename, enabled=enabled, order=order)
    db.add(script)
    db.commit()
    db.refresh(script)
    return {"id": script.id, "name": script.name}


def toggle_script(db: Session, script_id: int) -> dict:
    script = db.query(WorkScript).filter(WorkScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script no encontrado")
    script.enabled = not script.enabled
    db.commit()
    return {"id": script.id, "name": script.name, "enabled": script.enabled}


def generate_launch(db: Session) -> dict:
    scripts = db.query(WorkScript).filter(WorkScript.enabled == True).order_by(WorkScript.order).all()

    included = []
    tabs = []
    for s in scripts:
        path = os.path.join(SCRIPTS_DIR, s.filename)
        if not os.path.isfile(path):
            continue
        tabs.append((s.title, path))
        included.append(s.name)

    lines = ["#!/bin/bash", "", 'echo "🚀 Abriendo pestañas..."', ""]
    if tabs:
        cmd = "gnome-terminal --window"
        for title, path in tabs:
            cmd += f' --tab --title="{title}" -e "bash {path}"'
        lines.append(cmd)
    lines += ["", 'echo "✅ Listo."']

    os.makedirs(os.path.dirname(LAUNCH_SH), exist_ok=True)
    with open(LAUNCH_SH, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(LAUNCH_SH, 0o700)

    return {"generated": LAUNCH_SH, "scripts_included": included}


def run_launch() -> dict:
    if not os.path.isfile(LAUNCH_SH):
        raise HTTPException(status_code=404, detail="launch.sh no existe, generalo primero")
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    subprocess.Popen(
        ["bash", LAUNCH_SH],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    return {"status": "launched"}
