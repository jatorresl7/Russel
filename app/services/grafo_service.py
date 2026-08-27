"""El grafo de estados de Russ.

La regla que sostiene todo el diseño: **el grafo es determinista y el modelo
solo se invoca en las hojas**. Quien esta en cuadro, cuanto hace que no habla,
si ya dijo esto — todo eso son comparaciones baratas. Preguntarle al LLM en
cada vuelta "deberia decir algo?" serian segundos de CPU cada vez, robados a
whisper y a YOLO, para casi siempre contestar que no.

    latente ──(evento del mundo)──> atento ──(vale la pena)──> resolviendo
       ^                              │                            │
       │                              └──(cooldown / ya lo dijo)───┘
       │                                                           │
       └───────────────(respuesta emitida)─────────────────────────┘

`resolviendo` puede bajar a `actuando` (una tool) y volver. Y desde `latente`,
con la CPU libre, se pasa a `consolidando` para escribir memorias.

De los cinco estados, solo `resolviendo` y `consolidando` gastan modelo.

La iniciativa —la arista `latente -> atento`— viene APAGADA. Es la unica parte
que hace que Russ hable sin que le hablen, y es la que hay que ajustar viendola
fallar. Se prende con el modulo `iniciativa`.
"""
import collections
import threading
import time

from app.core import runtime

ESTADOS = ("latente", "atento", "resolviendo", "actuando", "consolidando")

# Cuanto tiene que pasar entre dos cosas dichas por iniciativa propia. Es el
# unico freno real contra un bot insoportable, y por eso es generoso: mas vale
# que se pierda un saludo a que comente cada vez que pasas por delante.
COOLDOWN_S = 90.0

# Cada cuanto mira el mundo cuando la iniciativa esta prendida. Barato: son
# lecturas de diccionarios en memoria, ningun modelo.
TICK_S = 1.5

_lock = threading.Lock()
_estado = "latente"
_desde = time.time()
_historia = collections.deque(maxlen=40)
_contadores = {e: 0 for e in ESTADOS}

# Quien publica los cambios a la consola. Lo registra assistant_service al
# importar: si grafo_service lo importara a el, seria un ciclo.
_emisor = None

# Lo ultimo que dijo por iniciativa propia, y cuando.
_ultima_iniciativa = 0.0
_ultimo_motivo = ""
_caras_vistas: set[str] = set()
_disparador = None      # lo pone assistant_service: como se le pide que hable


def registrar(emisor=None, disparador=None):
    """assistant_service se presenta: por aca publico, por aca te pido que
    hables. Inyectado y no importado para no cerrar un ciclo de imports."""
    global _emisor, _disparador
    if emisor is not None:
        _emisor = emisor
    if disparador is not None:
        _disparador = disparador


def ir_a(nuevo: str, motivo: str = "") -> None:
    """Mueve el grafo y lo publica. Idempotente: repetir el estado actual no
    ensucia la historia, que es lo que se mira para entender que paso."""
    global _estado, _desde
    if nuevo not in ESTADOS:
        return
    with _lock:
        if nuevo == _estado:
            return
        anterior, _estado = _estado, nuevo
        ahora = time.time()
        paso = {"de": anterior, "a": nuevo, "motivo": motivo,
                "at": time.strftime("%H:%M:%S"),
                "duro_ms": int((ahora - _desde) * 1000)}
        _desde = ahora
        _historia.appendleft(paso)
        _contadores[nuevo] += 1
    if _emisor:
        # Sin `at`: lo pone `emitir()`, y mandarlo dos veces choca. El de `paso`
        # se conserva igual para la historia, que se lee por HTTP y no por SSE.
        _emisor("grafo", estado=nuevo, de=paso["de"], a=paso["a"],
                motivo=paso["motivo"], duro_ms=paso["duro_ms"])


def actual() -> str:
    with _lock:
        return _estado


# ── La politica: lo unico que decide si vale la pena hablar ─────────────────

def _vale_la_pena(motivo: str) -> tuple[bool, str]:
    """Sin modelo, sin red, sin nada caro.

    Devuelve (si, por que) — el por que se publica y se ve en la vista del
    grafo, que es como se ajusta esto sin adivinar.
    """
    if not runtime.activo("llm"):
        return False, "el llm esta apagado"
    ahora = time.time()
    if ahora - _ultima_iniciativa < COOLDOWN_S:
        faltan = int(COOLDOWN_S - (ahora - _ultima_iniciativa))
        return False, f"cooldown, faltan {faltan}s"
    if motivo == _ultimo_motivo:
        return False, "ya dijo algo por esto mismo"
    return True, motivo


def _eventos_del_mundo() -> list[str]:
    """Que cambio ahi afuera desde la ultima vuelta.

    Hoy solo mira caras porque es lo unico que el sistema sabe reconocer de
    verdad; `lo_que_veo()` da objetos, pero "aparecio una silla" no es un
    evento por el que valga la pena hablar.
    """
    global _caras_vistas
    from app.services import face_service
    try:
        est = face_service.estado()
    except Exception:
        return []
    ahora = {v["nombre"] for v in est["tracks"].values() if v.get("nombre")}
    nuevas = ahora - _caras_vistas
    _caras_vistas = ahora
    return [f"aparecio {n}" for n in sorted(nuevas)]


def _vigilante():
    """El lazo de la iniciativa. Solo corre cuando el modulo esta prendido."""
    global _ultima_iniciativa, _ultimo_motivo
    while True:
        time.sleep(TICK_S)
        if not runtime.activo("iniciativa"):
            continue
        if actual() != "latente":
            continue          # ya esta ocupado en algo
        for motivo in _eventos_del_mundo():
            ir_a("atento", motivo)
            ok, razon = _vale_la_pena(motivo)
            if not ok:
                ir_a("latente", razon)
                continue
            _ultima_iniciativa = time.time()
            _ultimo_motivo = motivo
            if _disparador:
                _disparador(motivo)
            break


threading.Thread(target=_vigilante, daemon=True, name="russ-grafo").start()


def estado() -> dict:
    with _lock:
        return {
            "estado": _estado,
            "desde_ms": int((time.time() - _desde) * 1000),
            "historia": list(_historia),
            "contadores": dict(_contadores),
            "iniciativa": runtime.activo("iniciativa"),
            "cooldown_s": COOLDOWN_S,
            "cooldown_restante_s": max(
                0, round(COOLDOWN_S - (time.time() - _ultima_iniciativa), 1))
            if _ultima_iniciativa else 0,
            "ultimo_motivo": _ultimo_motivo,
            "estados": list(ESTADOS),
        }
