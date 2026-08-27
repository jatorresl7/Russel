import subprocess
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db import Tool, ScriptRun


def list_tools(db: Session) -> list:
    tools = db.query(Tool).filter(Tool.enabled == True).all()
    return [{"id": t.id, "name": t.name, "description": t.description, "command": t.command} for t in tools]


def create_tool(db: Session, name: str, description: str, command: str) -> dict:
    tool = Tool(name=name, description=description, command=command)
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return {"id": tool.id, "name": tool.name}


def run_tool(db: Session, tool_id: int) -> dict:
    tool = db.query(Tool).filter(Tool.id == tool_id, Tool.enabled == True).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool no encontrada")

    result = subprocess.run(tool.command, shell=True, capture_output=True, text=True, timeout=60)
    status = "success" if result.returncode == 0 else "error"
    output = result.stdout + result.stderr

    db.add(ScriptRun(tool_id=tool.id, output=output, status=status))
    db.commit()

    return {"status": status, "output": output}
