from fastapi import APIRouter
from pydantic import BaseModel

from app.core import runtime

router = APIRouter(prefix="/system", tags=["system"])


class Toggle(BaseModel):
    modulo: str
    on: bool


@router.get("")
def estado():
    return runtime.estado()


@router.post("/toggle")
def toggle(body: Toggle):
    return runtime.activar(body.modulo, body.on)
