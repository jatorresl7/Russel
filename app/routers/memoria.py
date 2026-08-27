from fastapi import APIRouter
from pydantic import BaseModel

from app.services import memoria_service, llm_service

router = APIRouter(prefix="/memoria", tags=["memoria"])


class MemoriaNueva(BaseModel):
    texto: str
    tipo: str = "hecho"


class Consulta(BaseModel):
    texto: str
    k: int = 4


@router.get("")
def listar(q: str = "", tipo: str = "", fuente: str = "",
           page: int = 0, size: int = 50, search: str = ""):
    """Devuelve el mismo envoltorio `Page` que espera `CrudService.findPage`.
    `search` es el nombre que usa el front generico; `q` el que se lee mejor
    desde curl. Los dos hacen lo mismo."""
    return memoria_service.listar(q=q or search, tipo=tipo, fuente=fuente,
                                  page=page, size=size)


@router.get("/estado")
def estado():
    return memoria_service.estado()


@router.post("")
def crear(body: MemoriaNueva):
    """Alta a mano desde la vista de conocimiento: lo que le enseñas vos, no lo
    que aprendio solo."""
    return memoria_service.guardar(body.texto, tipo=body.tipo, fuente="explicito")


@router.put("/{id_}")
def editar(id_: int, body: MemoriaNueva):
    return memoria_service.editar(id_, body.texto)


@router.delete("/{id_}")
def olvidar(id_: int):
    return memoria_service.olvidar(id_)


class Vigencia(BaseModel):
    vigente: bool = True


@router.patch("/{id_}/vigente")
def aprobar(id_: int, body: Vigencia):
    """Lo que sale de la consolidacion nace en espera; esto lo habilita."""
    return memoria_service.aprobar(id_, body.vigente)


@router.post("/buscar")
def buscar(body: Consulta):
    """Ver que recuperaria Russ para una frase, sin gastarle un turno."""
    return memoria_service.buscar(body.texto, k=body.k)


@router.post("/consolidar")
def consolidar():
    """Fuerza una vuelta ya, sin esperar a que la CPU quede libre."""
    return memoria_service.consolidar(lambda msgs: llm_service.generar(msgs))
