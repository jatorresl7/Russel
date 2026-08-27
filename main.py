import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routers import (gmail, tools, work_scripts, chat, vision, robot,
                         audio, system, assistant, faces, memoria, grafo)

app = FastAPI(title="Jarvis API")


@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        # Sin postgres se pierden los historiales, pero audio, vision y el
        # LLM local no dependen de la DB para funcionar.
        print(f"[jarvis] DB no disponible ({type(e).__name__}); sigo sin ella.")


@app.on_event("shutdown")
def shutdown():
    # Corta el generador del stream para que uvicorn pueda reiniciar.
    vision.vision_service.apagar()


# La API entera cuelga de /api. La raiz es del front, asi que una vista
# nueva (/tools, /scripts) no puede chocar nunca con un endpoint.
API = "/api"

app.include_router(gmail.router, prefix=API)
app.include_router(tools.router, prefix=API)
app.include_router(work_scripts.router, prefix=API)
app.include_router(chat.router, prefix=API)
app.include_router(vision.router, prefix=API)
app.include_router(robot.router, prefix=API)
app.include_router(audio.router, prefix=API)
app.include_router(system.router, prefix=API)
app.include_router(assistant.router, prefix=API)
app.include_router(faces.router, prefix=API)
app.include_router(memoria.router, prefix=API)
app.include_router(grafo.router, prefix=API)

# ── Front ───────────────────────────────────────────────────────────────────
# El front es la SPA de web/ (fuente en src/, bundle en web/dist via `npm run
# build`). Lo sirve este mismo uvicorn; apiUrl en web/config.js es '/api/'.
WEB = os.path.join(os.path.dirname(__file__), "web")
DIST = os.path.join(WEB, "dist")
INDEX = os.path.join(WEB, "index.html")

# Sin `npm run build` todavia no existe: se crea vacio para que el mount no
# reviente al arrancar. La SPA sale en blanco hasta que se compile.
os.makedirs(DIST, exist_ok=True)
app.mount("/dist", StaticFiles(directory=DIST), name="dist")

# Todo lo que ya atiende alguien: /api, /dist y lo que monta FastAPI (/docs,
# /openapi.json). Se calcula aca, con los routers ya incluidos y ANTES del
# catch-all, para que lo que se agregue arriba entre solo.
RUTAS_API = {
    r.path.strip("/").split("/")[0]
    for r in app.routes
    if getattr(r, "path", "").strip("/")
}


@app.get("/config.js", include_in_schema=False)
def config_js():
    return FileResponse(os.path.join(WEB, "config.js"), media_type="application/javascript")


@app.get("/{ruta:path}", include_in_schema=False)
def spa(ruta: str):
    """Cualquier ruta del front devuelve el index: el router vive en el
    navegador, asi que recargar en /scripts tiene que servir la misma pagina.
    Lo que cae en un prefijo de la API y no matcheo antes es un 404 de verdad,
    no una vista."""
    if ruta.split("/")[0] in RUTAS_API:
        raise HTTPException(status_code=404)
    return FileResponse(INDEX)
