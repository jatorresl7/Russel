"""Traduce las senales de vision (giro/avance) a velocidades de las 4 ruedas
mecanum, con suavizado y limite de aceleracion.

Convencion de ruedas, vista desde arriba con el frente hacia arriba:

    fl  ----  fr
     |        |
    rl  ----  rr
"""
import time

MAX_STEP = 0.08      # cambio maximo de velocidad por tick (protege motores y bateria)
SMOOTH = 0.35        # suavizado exponencial de la entrada de vision
TURN_GAIN = 0.9
FORWARD_GAIN = 0.8
STRAFE_GAIN = 0.0    # las mecanum pueden desplazarse de lado; apagado por defecto

WHEELS = ("fl", "fr", "rl", "rr")

_smoothed = {"turn": 0.0, "forward": 0.0, "strafe": 0.0}
_wheels = {w: 0.0 for w in WHEELS}
_last_seen = 0.0
_enabled = False


def mecanum(forward: float, strafe: float, turn: float) -> dict:
    """Cinematica inversa mecanum. Devuelve velocidades normalizadas -1..1."""
    raw = {
        "fl": forward + strafe + turn,
        "fr": forward - strafe - turn,
        "rl": forward - strafe + turn,
        "rr": forward + strafe - turn,
    }
    # si alguna se pasa de 1, escalar todas igual para no deformar el vector
    mayor = max(abs(v) for v in raw.values())
    if mayor > 1.0:
        raw = {k: v / mayor for k, v in raw.items()}
    return {k: round(v, 3) for k, v in raw.items()}


def _ramp(actual: float, objetivo: float) -> float:
    delta = objetivo - actual
    if delta > MAX_STEP:
        delta = MAX_STEP
    elif delta < -MAX_STEP:
        delta = -MAX_STEP
    return actual + delta


def update(control: dict) -> dict:
    """Recibe la salida de vision_service y actualiza las ruedas."""
    global _last_seen

    if control.get("has_target") and _enabled:
        objetivo = {
            "turn": control["turn"] * TURN_GAIN,
            "forward": control["forward"] * FORWARD_GAIN,
            "strafe": control["turn"] * STRAFE_GAIN,
        }
        _last_seen = time.time()
    else:
        objetivo = {"turn": 0.0, "forward": 0.0, "strafe": 0.0}

    for k in _smoothed:
        _smoothed[k] += SMOOTH * (objetivo[k] - _smoothed[k])

    destino = mecanum(_smoothed["forward"], _smoothed["strafe"], _smoothed["turn"])
    for w in WHEELS:
        _wheels[w] = round(_ramp(_wheels[w], destino[w]), 3)

    return state()


def state() -> dict:
    return {
        "enabled": _enabled,
        "wheels": dict(_wheels),
        "smoothed": {k: round(v, 3) for k, v in _smoothed.items()},
        "seen_ago": round(time.time() - _last_seen, 2) if _last_seen else None,
    }


def enable(on: bool) -> dict:
    global _enabled
    _enabled = on
    return state()


def stop() -> dict:
    for w in WHEELS:
        _wheels[w] = 0.0
    for k in _smoothed:
        _smoothed[k] = 0.0
    return state()


# --- lazo de control a frecuencia fija ---------------------------------------
import threading  # noqa: E402

from app.services import vision_service  # noqa: E402

HZ = 20.0
_loop = None
_loop_lock = threading.Lock()


def _control_loop():
    periodo = 1.0 / HZ
    while True:
        update(vision_service.last_control())
        time.sleep(periodo)


def ensure_loop() -> None:
    global _loop
    with _loop_lock:
        if _loop is not None and _loop.is_alive():
            return
        _loop = threading.Thread(target=_control_loop, daemon=True)
        _loop.start()
