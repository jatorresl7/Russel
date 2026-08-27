from fastapi import APIRouter

from app.services import grafo_service

router = APIRouter(prefix="/grafo", tags=["grafo"])


@router.get("")
def estado():
    """Estado actual, historia de transiciones y por que la politica dijo que
    si o que no. Es lo que se mira para ajustar la iniciativa."""
    return grafo_service.estado()
