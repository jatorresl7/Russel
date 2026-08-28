"""La busqueda web: estado y prueba manual."""
from fastapi import APIRouter, Request

from app.services import busqueda_service

router = APIRouter(prefix="/busqueda", tags=["busqueda"])


@router.get("/estado")
def estado():
    return busqueda_service.estado()


@router.get("/historial")
def historial():
    """Que leyo de la web, con el texto completo. Es lo unico que permite
    distinguir «el buscador trajo basura» de «lo tenia bien y contesto otra
    cosa» — que se arreglan en lados opuestos."""
    return busqueda_service.historial()


@router.post("/probar")
async def probar(request: Request):
    """Para ver que devolveria una frase, y si dispararia siquiera."""
    datos = await request.json()
    texto = datos.get("texto", "")
    dispara = busqueda_service.hace_falta(texto)
    return {"texto": texto, "dispara": dispara,
            "resultados": busqueda_service.buscar(texto) if dispara else []}
