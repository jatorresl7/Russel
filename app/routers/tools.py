from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import tools_service

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolCreate(BaseModel):
    name: str
    description: str = ""
    command: str


@router.get("")
def list_tools(db: Session = Depends(get_db)):
    return tools_service.list_tools(db)


@router.post("")
def create_tool(body: ToolCreate, db: Session = Depends(get_db)):
    return tools_service.create_tool(db, body.name, body.description, body.command)


@router.post("/{tool_id}/run")
def run_tool(tool_id: int, db: Session = Depends(get_db)):
    return tools_service.run_tool(db, tool_id)

