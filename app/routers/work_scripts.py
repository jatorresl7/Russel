from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import work_scripts_service

router = APIRouter(prefix="/work-scripts", tags=["work-scripts"])


class WorkScriptCreate(BaseModel):
    name: str
    title: str
    filename: str
    enabled: bool = True
    order: int = 0


@router.get("")
def list_scripts(db: Session = Depends(get_db)):
    return work_scripts_service.list_scripts(db)


@router.post("")
def create_script(body: WorkScriptCreate, db: Session = Depends(get_db)):
    return work_scripts_service.create_script(db, body.name, body.title, body.filename, body.enabled, body.order)


@router.patch("/{script_id}/toggle")
def toggle_script(script_id: int, db: Session = Depends(get_db)):
    return work_scripts_service.toggle_script(db, script_id)


@router.post("/generate")
def generate_launch(db: Session = Depends(get_db)):
    return work_scripts_service.generate_launch(db)


@router.post("/run")
def run_launch():
    return work_scripts_service.run_launch()
