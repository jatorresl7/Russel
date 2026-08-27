import json
import queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import assistant_service, llm_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


class Mensaje(BaseModel):
    text: str


@router.get("/status")
def status():
    return assistant_service.estado()


@router.post("/ask")
def ask(body: Mensaje):
    """Entrada por teclado. Vuelve enseguida: la respuesta sale por /stream."""
    return assistant_service.encolar(body.text, origen="texto")


@router.get("/contexto")
def contexto():
    """Con que penso el ultimo turno: que veia, que recordo y cuanto ocupaba."""
    return assistant_service.contexto()


@router.post("/clear")
def clear():
    return assistant_service.limpiar()


@router.post("/load")
def load():
    llm_service.cargar()
    return llm_service.estado()


@router.post("/unload")
def unload():
    return llm_service.descargar()


@router.get("/stream")
def stream():
    """SSE: un evento por token. Es la unica forma de que se sienta rapido
    un modelo que en CPU va a ~12 tok/s."""
    q = assistant_service.suscribir()

    def eventos():
        try:
            yield ": conectado\n\n"
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"      # mantiene viva la conexion
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            assistant_service.desuscribir(q)

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
