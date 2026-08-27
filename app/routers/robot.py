from fastapi import APIRouter
from pydantic import BaseModel

from app.services import robot_service

router = APIRouter(prefix="/robot", tags=["robot"])

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis - Robot</title>
<style>
 *{box-sizing:border-box} body{margin:0;background:#14161a;color:#e8e8ea;
   font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:18px}
 h1{font-size:19px;margin:0 0 2px;font-weight:600}
 .sub{color:#9aa0ab;font-size:13px;margin-bottom:14px}
 .wrap{max-width:1180px;margin:0 auto}
 .grid{display:grid;grid-template-columns:1fr 330px;gap:14px}
 @media(max-width:860px){.grid{grid-template-columns:1fr}}
 img,canvas{width:100%;border-radius:9px;background:#000;display:block}
 .panel{background:#1c1f26;border:1px solid #282d37;border-radius:10px;padding:13px}
 h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#9aa0ab;
    margin:0 0 9px;font-weight:600}
 .row{display:flex;gap:7px;margin:10px 0 0;flex-wrap:wrap}
 button{background:#252932;color:#e8e8ea;border:1px solid #363b47;padding:8px 13px;
   border-radius:7px;cursor:pointer;font-size:13.5px;flex:1;white-space:nowrap}
 button:hover{background:#2e333e}
 button.on{background:#2a6df4;border-color:#2a6df4}
 button.go{background:#1f9d55;border-color:#1f9d55}
 button.stop{background:#c0392b;border-color:#c0392b}
 .w{display:flex;align-items:center;gap:8px;margin:7px 0;font-size:13px}
 .w b{width:22px;color:#9aa0ab;font-weight:500}
 .bar{flex:1;height:13px;background:#11141a;border-radius:4px;position:relative;overflow:hidden}
 .fill{position:absolute;top:0;bottom:0;left:50%;transition:width .08s,left .08s}
 .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#3a4150;z-index:2}
 .val{width:44px;text-align:right;font-variant-numeric:tabular-nums;color:#c8ccd4;font-size:12.5px}
 .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:8px;margin-top:12px}
 .card{background:#171a20;border:1px solid #262b34;border-radius:8px;padding:8px 10px}
 .k{font-size:10.5px;color:#9aa0ab;text-transform:uppercase;letter-spacing:.04em}
 .v{font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}
 #tr{margin-top:13px;max-height:250px;overflow-y:auto}
 .t{padding:9px 11px;background:#171a20;border-left:3px solid #2a6df4;
    border-radius:0 7px 7px 0;margin-bottom:7px}
 .t .m{font-size:11px;color:#767d89;margin-bottom:2px}
 .lvl{height:7px;background:#11141a;border-radius:4px;overflow:hidden;margin-top:9px;position:relative}
 .lvlf{height:100%;width:0;background:#1f9d55;transition:width .1s}
 .thr{position:absolute;top:0;bottom:0;width:2px;background:#e0b000}
 .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3a4150;margin-right:6px}
 .dot.live{background:#1f9d55;box-shadow:0 0 7px #1f9d55}
 .dot.hot{background:#e0b000;box-shadow:0 0 7px #e0b000}
</style></head><body><div class="wrap">
<h1>Jarvis &mdash; robot</h1>
<div class="sub">Todo local. Sin GPU los m&oacute;dulos compiten por la CPU: apag&aacute; el que no
est&eacute;s usando.</div>
<div class="panel" style="margin-bottom:14px">
  <h2>M&oacute;dulos &mdash; <span id="dev">?</span></h2>
  <div class="row" id="mods"></div>
</div>
<div class="grid">
  <div class="panel">
    <h2>C&aacute;mara</h2>
    <img src="/api/vision/stream">
    <div class="row">
      <button id="bSeg">Segmentaci&oacute;n</button>
      <button id="bAll">Todas las clases</button>
      <button id="bReset">Soltar objetivo</button>
    </div>
    <div class="stats">
      <div class="card"><div class="k">Giro</div><div class="v" id="turn">0.00</div></div>
      <div class="card"><div class="k">Avance</div><div class="v" id="fwd">0.00</div></div>
      <div class="card"><div class="k">Track</div><div class="v" id="tid">&mdash;</div></div>
      <div class="card"><div class="k">FPS</div><div class="v" id="fps">&mdash;</div></div>
    </div>
  </div>
  <div class="panel">
    <h2>Movimiento</h2>
    <canvas id="sim" width="300" height="210"></canvas>
    <div id="wheels" style="margin-top:10px"></div>
    <div class="row">
      <button id="bGo" class="go">Seguirme</button>
      <button id="bStop" class="stop">PARAR</button>
    </div>
  </div>
</div>
<div class="panel" style="margin-top:14px">
  <h2><span class="dot" id="dot"></span>Escucha &mdash; <span id="mstat">detenida</span></h2>
  <div class="lvl"><div class="lvlf" id="lvl"></div><div class="thr" id="thr"></div></div>
  <div class="row">
    <button id="bMic">Empezar a escuchar</button>
    <button id="bClr">Limpiar</button>
  </div>
  <div id="par" class="t" style="display:none;border-left-color:#e0b000">
    <div class="m">confirmado &middot; LocalAgreement</div>
    <span id="conf"></span><span id="pend" style="opacity:.45;font-style:italic"></span>
    <div class="m" style="margin-top:7px">instant&aacute;neo &middot; vosk</div>
    <div id="vosk" style="opacity:.6;font-size:13.5px"></div></div>
  <div id="tr"><div id="vacio" style="color:#767d89;font-size:13px">Sin transcripciones todav&iacute;a.</div></div>
</div></div>
<script>
const W=['fl','fr','rl','rr'], cont=document.getElementById('wheels');
W.forEach(w=>cont.insertAdjacentHTML('beforeend',
 `<div class="w"><b>${w}</b><div class="bar"><div class="mid"></div>
  <div class="fill" id="f_${w}"></div></div><div class="val" id="v_${w}">0.00</div></div>`));

let seg=false, all=false, on=false, mic=false;
const $=i=>document.getElementById(i);
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},
                          body:b?JSON.stringify(b):null});

$('bSeg').onclick=()=>{seg=!seg;$('bSeg').classList.toggle('on',seg);
  post('/api/vision/config',{seg:seg,all_classes:all})};
$('bAll').onclick=()=>{all=!all;$('bAll').classList.toggle('on',all);
  post('/api/vision/config',{seg:seg,all_classes:all})};
$('bReset').onclick=()=>post('/api/vision/reset');
$('bGo').onclick=()=>{on=!on;$('bGo').textContent=on?'Siguiendo':'Seguirme';
  $('bGo').classList.toggle('on',on); post('/api/robot/enable',{on:on})};
$('bStop').onclick=()=>{on=false;$('bGo').textContent='Seguirme';
  $('bGo').classList.remove('on'); post('/api/robot/stop')};
$('bMic').onclick=async()=>{mic=!mic;$('bMic').textContent=mic?'Cargando modelo...':'Empezar a escuchar';
  $('bMic').classList.toggle('on',mic); await post(mic?'/api/audio/start':'/api/audio/stop')};
$('bClr').onclick=()=>post('/api/audio/clear');

const MODS=[['vision','Visi\u00f3n'],['asr_stream','ASR vivo'],['asr_final','ASR final'],['llm','LLM']];
async function pintarMods(){
  const st=await(await fetch('/api/system')).json();
  $('dev').textContent=st.gpu?('GPU \u00b7 '+st.device):('CPU \u00b7 '+st.total_hilos+' hilos');
  $('mods').innerHTML=MODS.map(([k,n])=>{
    const m=st.modulos[k]||{};
    return `<button data-m="${k}" class="${m.activo?'on':''}">${n} <span style="opacity:.6">${m.hilos}h</span></button>`;
  }).join('');
  $('mods').querySelectorAll('button').forEach(b=>b.onclick=async()=>{
    const k=b.dataset.m, on=!b.classList.contains('on');
    await post('/api/system/toggle',{modulo:k,on:on}); pintarMods();
  });
}
pintarMods(); setInterval(pintarMods, 4000);

(async()=>{try{const c=await(await fetch('/api/vision/config')).json();
  seg=!!c.seg; all=!!c.all_classes;
  $('bSeg').classList.toggle('on',seg); $('bAll').classList.toggle('on',all);}catch(e){}})();

const cv=$('sim'), cx=cv.getContext('2d');
let px=150, py=105, th=-Math.PI/2;
function dibujar(wh){
  const vy=(wh.fl+wh.fr+wh.rl+wh.rr)/4, vx=(wh.fl-wh.fr-wh.rl+wh.rr)/4,
        om=(wh.fl-wh.fr+wh.rl-wh.rr)/4;
  th+=om*0.06;
  px+=(vy*Math.cos(th)-vx*Math.sin(th))*1.6; py+=(vy*Math.sin(th)+vx*Math.cos(th))*1.6;
  px=Math.max(20,Math.min(cv.width-20,px)); py=Math.max(20,Math.min(cv.height-20,py));
  cx.fillStyle='#0d0f13'; cx.fillRect(0,0,cv.width,cv.height);
  cx.strokeStyle='#1e232c';
  for(let i=0;i<cv.width;i+=30){cx.beginPath();cx.moveTo(i,0);cx.lineTo(i,cv.height);cx.stroke();}
  for(let j=0;j<cv.height;j+=30){cx.beginPath();cx.moveTo(0,j);cx.lineTo(cv.width,j);cx.stroke();}
  cx.save(); cx.translate(px,py); cx.rotate(th);
  cx.fillStyle='#2a6df4'; cx.fillRect(-15,-11,30,22);
  cx.fillStyle='#e8e8ea'; cx.beginPath(); cx.moveTo(15,0); cx.lineTo(6,-6); cx.lineTo(6,6);
  cx.closePath(); cx.fill(); cx.fillStyle='#11141a';
  [[-11,-13],[7,-13],[-11,9],[7,9]].forEach(p=>cx.fillRect(p[0],p[1],7,4));
  cx.restore();
}

setInterval(async()=>{
  try{
    const c=await(await fetch('/api/vision/control')).json();
    $('turn').textContent=c.turn.toFixed(2); $('fwd').textContent=c.forward.toFixed(2);
    $('tid').textContent=c.has_target?('#'+c.track_id):'\u2014';
    $('fps').textContent=c.fps!=null?c.fps.toFixed(1):'\u2014';
    const s=await(await fetch('/api/robot/state')).json();
    W.forEach(w=>{const v=s.wheels[w], f=$('f_'+w);
      f.style.width=(Math.abs(v)*50)+'%'; f.style.left=v>=0?'50%':(50-Math.abs(v)*50)+'%';
      f.style.background=v>=0?'#2a6df4':'#c0392b'; $('v_'+w).textContent=v.toFixed(2);});
    dibujar(s.wheels);
  }catch(e){}
},70);

setInterval(async()=>{
  try{
    const a=await(await fetch('/api/audio/status')).json();
    $('dot').className='dot'+(a.speaking?' hot':(a.listening?' live':''));
    $('mstat').textContent=(!a.listening?'detenida':(a.speaking?'hablando...':'esperando voz'))
      +'  \u00b7 vad '+(a.vad!=null?a.vad.toFixed(2):'-')
      +(a.pasadas?'  \u00b7 '+a.pasadas+' pasadas ('+a.ultima_pasada_ms+'ms)':'')
      +(a.buffer_s?'  \u00b7 buffer '+a.buffer_s+'s':'')
      +(a.dropped?'  \u00b7 '+a.dropped+' PERDIDOS':'');
    if(a.listening) $('bMic').textContent='Escuchando';
    $('lvl').style.width=Math.min(100,(a.vad||0)*100)+'%';
    $('lvl').style.background=a.speaking?'#e0b000':'#1f9d55';
    $('thr').style.display='none';
    const vivo=(a.committed||'')+(a.pending||'')+(a.vosk||'');
    if(vivo){ $('par').style.display='block';
      $('conf').textContent=a.committed?a.committed+' ':'';
      $('pend').textContent=a.pending||'';
      $('vosk').textContent=a.vosk||'\u2014'; }
    else { $('par').style.display='none'; }
    const tr=$('tr');
    if(a.transcripts.length){
      tr.innerHTML=a.transcripts.map(t=>
        `<div class="t"><div class="m">${t.at} &middot; ${t.dur}s &middot; whisper ${t.took}s</div>${t.text}`
        + `</div>`).join('');
    }
  }catch(e){}
},180);
</script></body></html>"""


class Enable(BaseModel):
    on: bool


@router.get("")
def page():
    from fastapi.responses import HTMLResponse
    robot_service.ensure_loop()
    return HTMLResponse(PAGE)


@router.get("/state")
def state():
    robot_service.ensure_loop()
    return robot_service.state()


@router.get("/command")
def command():
    """Lo que el robot real va a consultar 20 veces por segundo."""
    robot_service.ensure_loop()
    return robot_service.state()["wheels"]


@router.post("/enable")
def enable(body: Enable):
    robot_service.ensure_loop()
    return robot_service.enable(body.on)


@router.post("/stop")
def stop():
    robot_service.enable(False)
    return robot_service.stop()
