"""La voz: elegir cual, probarla, y los sonidos de cada evento."""
from fastapi import APIRouter, Request, UploadFile, File

from app.services import tts_service

router = APIRouter(prefix="/tts", tags=["tts"])


@router.get("/estado")
def estado():
    return tts_service.estado()


@router.get("/voces")
def voces():
    return tts_service.voces()


@router.post("/voz")
async def elegir(request: Request):
    datos = await request.json()
    return tts_service.elegir(datos.get("voz", ""))


@router.post("/probar")
async def probar(request: Request):
    """Prueba una voz y un timbre SIN guardarlos. Es la diferencia entre un
    panel donde se compara y uno donde hay que elegir a ciegas y deshacer."""
    datos = await request.json()
    texto = datos.get("texto") or "Hola, soy Russ. Asi es como sueno."
    voz = datos.get("voz")
    preset = datos.get("robot")
    ajustes = datos.get("ajustes")
    sint = datos.get("params")
    if voz:
        previa = tts_service.voz_actual()
        tts_service.elegir(voz)
        r = tts_service.decir(texto, preset, ajustes, sint, prueba=True)
        if previa:
            tts_service.elegir(previa)
        return r
    return tts_service.decir(texto, preset, ajustes, sint, prueba=True)


@router.get("/robot")
def leer_robot():
    return tts_service.robot()


@router.post("/robot")
async def guardar_robot(request: Request):
    datos = await request.json()
    return tts_service.robot(datos.get("preset"), datos.get("ajustes"))


@router.post("/decir")
async def decir(request: Request):
    datos = await request.json()
    return tts_service.decir(datos.get("texto", ""))


@router.post("/volumen")
async def volumen(request: Request):
    datos = await request.json()
    return {"volumen": tts_service.volumen(datos.get("volumen"))}


@router.get("/parametros")
def parametros():
    """Todo lo que la libreria deja tocar de la sintesis, con rangos y con lo
    que trae la voz activa por defecto."""
    return tts_service.parametros()


@router.post("/parametros")
async def guardar_parametros(request: Request):
    datos = await request.json()
    return {"actual": tts_service.params(datos.get("voz"), datos.get("params") or {})}


@router.get("/catalogo")
def catalogo(idioma: str = "", buscar: str = ""):
    """Todo lo que se puede bajar. Sirve cualquier idioma: la fonemizacion es
    aparte, asi que una voz japonesa igual habla español."""
    return tts_service.catalogo(idioma or None, buscar)


@router.post("/catalogo/{nombre}")
def bajar(nombre: str):
    return tts_service.bajar(nombre)


@router.delete("/voces/{nombre}")
def borrar_voz(nombre: str):
    return tts_service.borrar_voz(nombre)


@router.post("/fonemas")
async def fonemas(request: Request):
    datos = await request.json()
    return {"fonemas": tts_service.idioma_fonemas(datos.get("idioma"))}


@router.get("/sonidos")
def sonidos():
    return tts_service.sonidos()


@router.post("/sonidos/{evento}")
async def subir(evento: str, archivo: UploadFile = File(...)):
    return tts_service.guardar_sonido(evento, await archivo.read())


@router.post("/sonidos/{evento}/probar")
def probar_sonido(evento: str):
    return tts_service.sonar(evento, prueba=True)


@router.post("/parar")
def parar():
    """Calla a Russ ya. Vacia la cola y mata lo que este sonando."""
    return tts_service.parar()


@router.delete("/sonidos/{evento}")
def borrar(evento: str):
    return tts_service.borrar_sonido(evento)
