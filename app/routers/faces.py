import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.services import face_service

router = APIRouter(prefix="/faces", tags=["faces"])


class Nombre(BaseModel):
    nombre: str
    fotos: int = 5


@router.get("", response_class=HTMLResponse)
def page():
    """Galeria de lo enrolado. Existe para poder revisar: el vector no se
    puede mirar, el recorte si."""
    est = face_service.estado()
    filas = []
    for nombre, n in est["conocidos"].items():
        imgs = "".join(
            f'<img src="/api/faces/{nombre}/foto/{os.path.basename(f)}" title="{os.path.basename(f)}">'
            for f in face_service.fotos_de(nombre))
        filas.append(f'<h2>{nombre} <small>{n} vectores</small></h2>'
                     f'<div class="tira">{imgs or "<i>sin recortes guardados</i>"}</div>')

    vistos = "".join(
        f'<li>track #{t}: <b>{v["nombre"] or "desconocido"}</b> '
        f'<code>{v["score"]}</code></li>'
        for t, v in est["tracks"].items()) or "<li><i>nadie en cuadro</i></li>"

    return f"""<!doctype html><meta charset="utf-8"><title>Caras</title>
<style>
 body{{background:#0e1116;color:#e6edf3;font:15px system-ui;margin:0;padding:20px}}
 h1{{font-size:17px}} h2{{font-size:15px;margin:22px 0 8px}}
 small{{color:#8b949e;font-weight:400}}
 .tira{{display:flex;gap:8px;flex-wrap:wrap}}
 .tira img{{width:112px;height:112px;border-radius:8px;border:1px solid #262d36}}
 ul{{list-style:none;padding:0}} li{{padding:4px 0;border-bottom:1px solid #1c232c}}
 code{{color:#3fb950}} a{{color:#4c9aff}}
</style>
<h1>Caras enroladas</h1>
{"".join(filas) or "<p><i>ninguna. Enrolate con POST /faces/enrolar</i></p>"}
<h2>Viendo ahora <small>umbral {est['umbral']}</small></h2>
<ul>{vistos}</ul>
<p><a href="/api/vision">camara en vivo</a> · <a href="/">chat</a></p>
<script>setTimeout(()=>location.reload(),2000)</script>"""


@router.get("/estado")
def estado():
    return face_service.estado()


@router.get("/{nombre}/fotos")
def fotos(nombre: str):
    """Los nombres de los recortes guardados de una persona.

    La galeria los necesita para armar los <img>. Antes esta ruta no existia
    porque la pagina se renderizaba en el server y leia el disco directo; con
    el front aparte hace falta pedirlos.
    """
    return [os.path.basename(f) for f in face_service.fotos_de(nombre)]


@router.get("/{nombre}/foto/{archivo}")
def foto(nombre: str, archivo: str):
    ruta = os.path.join(face_service.FOTOS_DIR, nombre, os.path.basename(archivo))
    if not os.path.isfile(ruta):
        raise HTTPException(404, "no existe")
    return FileResponse(ruta, media_type="image/jpeg")


@router.post("/enrolar")
def enrolar(body: Nombre):
    """Mira a la camara: toma varias fotos y guarda tus vectores."""
    return face_service.enrolar_desde_camara(body.nombre, fotos=body.fotos)


@router.delete("/{nombre}")
def olvidar(nombre: str):
    return face_service.olvidar(nombre)
