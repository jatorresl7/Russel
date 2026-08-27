from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app.services import vision_service

router = APIRouter(prefix="/vision", tags=["vision"])

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis - Vision</title>
<style>
 *{box-sizing:border-box} body{margin:0;background:#14161a;color:#e8e8ea;
   font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:20px}
 h1{font-size:18px;margin:0 0 14px;font-weight:600}
 .wrap{max-width:900px;margin:0 auto}
 img{width:100%;border-radius:10px;background:#000;display:block}
 .row{display:flex;gap:8px;margin:12px 0;flex-wrap:wrap}
 button{background:#252932;color:#e8e8ea;border:1px solid #363b47;padding:8px 14px;
   border-radius:7px;cursor:pointer;font-size:14px}
 button:hover{background:#2e333e} button.on{background:#2a6df4;border-color:#2a6df4}
 .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
 .card{background:#1c1f26;border:1px solid #282d37;border-radius:9px;padding:12px}
 .k{font-size:12px;color:#9aa0ab;text-transform:uppercase;letter-spacing:.04em}
 .v{font-size:22px;font-weight:600;margin-top:3px;font-variant-numeric:tabular-nums}
</style></head><body><div class="wrap">
<h1>Jarvis &mdash; visi&oacute;n</h1>
<img id="cam" src="/api/vision/stream">
<div class="row">
  <button id="bSeg">Segmentaci&oacute;n</button>
  <button id="bAll">Todas las clases</button>
  <button id="bReset">Soltar objetivo</button>
</div>
<div class="stats">
  <div class="card"><div class="k">Giro</div><div class="v" id="turn">0.00</div></div>
  <div class="card"><div class="k">Avance</div><div class="v" id="fwd">0.00</div></div>
  <div class="card"><div class="k">Objetivo</div><div class="v" id="tid">&mdash;</div></div>
  <div class="card"><div class="k">Alto caja</div><div class="v" id="dist">&mdash;</div></div>
  <div class="card"><div class="k">FPS</div><div class="v" id="fps">&mdash;</div></div>
</div></div>
<script>
let seg=false, all=false;
// El stream nunca se recarga: hay un solo hilo leyendo la camara y los
// botones solo cambian su configuracion.
async function aplicar(){
  document.getElementById('bSeg').classList.toggle('on',seg);
  document.getElementById('bAll').classList.toggle('on',all);
  await fetch('/api/vision/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({seg:seg,all_classes:all})});
}
document.getElementById('bSeg').onclick=()=>{seg=!seg;aplicar()};
document.getElementById('bAll').onclick=()=>{all=!all;aplicar()};
document.getElementById('bReset').onclick=()=>fetch('/api/vision/reset',{method:'POST'});
// El server manda: sincronizamos los botones con su estado real al cargar,
// si no la pagina puede mostrar 'apagado' con el modelo pesado corriendo.
(async()=>{
  try{ const c=await (await fetch('/api/vision/config')).json();
       seg=!!c.seg; all=!!c.all_classes;
       document.getElementById('bSeg').classList.toggle('on',seg);
       document.getElementById('bAll').classList.toggle('on',all);
  }catch(e){}
})();
setInterval(async()=>{
  try{
    const c=await (await fetch('/api/vision/control')).json();
    document.getElementById('turn').textContent=c.turn.toFixed(2);
    document.getElementById('fwd').textContent=c.forward.toFixed(2);
    document.getElementById('tid').textContent=c.has_target?('#'+c.track_id):'\\u2014';
    document.getElementById('dist').textContent=c.distance!=null?c.distance.toFixed(2):'\\u2014';
    document.getElementById('fps').textContent=c.fps!=null?c.fps.toFixed(1):'\\u2014';
  }catch(e){}
},300);
</script></body></html>"""


class Config(BaseModel):
    seg: bool | None = None
    all_classes: bool | None = None
    conf: float | None = None
    imgsz: int | None = None
    det_hz: float | None = None


@router.get("", response_class=HTMLResponse)
def page():
    return PAGE


@router.get("/stream")
def stream():
    return StreamingResponse(
        vision_service.mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/config")
def get_config():
    return vision_service.configure()


@router.post("/config")
def config(body: Config):
    return vision_service.configure(seg=body.seg, all_classes=body.all_classes,
                                    conf=body.conf, imgsz=body.imgsz,
                                    det_hz=body.det_hz)


@router.get("/control")
def control():
    return vision_service.last_control()


@router.post("/reset")
def reset():
    vision_service.reset_target()
    return {"ok": True}
