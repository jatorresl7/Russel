import collections
import os
import threading
import time

import cv2

# Presupuesto de CPU. La maquina tiene 16 hilos y hay tres consumidores
# pesados (YOLO, whisper final, whisper streaming). Sin repartir, se
# oversuscribe y el video se congela.
import numpy as np
import torch
from ultralytics import YOLO

from app.core import runtime
from app.services import face_service

# El presupuesto de hilos lo decide app/core/runtime.py, no este archivo.
# Se aplica al arrancar el worker y no en el import: si se aplica aca, un
# /system/toggle posterior no tiene ningun efecto sobre torch ni OpenCV.
def aplicar_hilos() -> int:
    n = runtime.hilos("vision")
    torch.set_num_threads(n)
    cv2.setNumThreads(n)
    return n

MODEL_DET = "yolo11n.pt"
MODEL_SEG = "yolo11n-seg.pt"
PERSON_CLASS = 0

TARGET_HEIGHT_RATIO = 0.60
TURN_DEADZONE = 0.12
FORWARD_DEADZONE = 0.15

VERDE = (80, 220, 120)
GRIS = (150, 150, 150)
AMARILLO = (60, 220, 250)
ROJO = (80, 80, 240)

_model = None
_model_name = None
_locked_id = None
_last_control = {"turn": 0.0, "forward": 0.0, "has_target": False, "distance": None}


def get_model(seg: bool = False) -> YOLO:
    global _model, _model_name
    name = MODEL_SEG if seg else MODEL_DET
    if _model is None or _model_name != name:
        _model = YOLO(name)
        _model_name = name
    return _model


def track(frame, classes: list | None = None, seg: bool = False, conf: float = 0.4,
          imgsz: int = 480) -> list:
    model = get_model(seg)
    results = model.track(frame, persist=True, classes=classes, conf=conf,
                          imgsz=imgsz, tracker="bytetrack.yaml", verbose=False)
    r = results[0]
    if r.boxes is None:
        return []

    names = r.names
    out = []
    for i, box in enumerate(r.boxes):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        out.append({
            "track_id": int(box.id[0]) if box.id is not None else None,
            "cls": int(box.cls[0]),
            "label": names[int(box.cls[0])],
            "conf": float(box.conf[0]),
            "box": (x1, y1, x2, y2),
            "area": (x2 - x1) * (y2 - y1),
            "mask": r.masks.xy[i] if seg and r.masks is not None else None,
        })
    return out


def pick_target(detections: list) -> dict | None:
    global _locked_id
    people = [d for d in detections if d["cls"] == PERSON_CLASS]
    if not people:
        return None

    if _locked_id is not None:
        for p in people:
            if p["track_id"] == _locked_id:
                return p

    target = max(people, key=lambda p: p["area"])
    _locked_id = target["track_id"]
    return target


def reset_target() -> None:
    global _locked_id
    _locked_id = None


NEUTRO = {"turn": 0.0, "forward": 0.0, "has_target": False,
          "track_id": None, "distance": None}


def last_control() -> dict:
    """Lo que consume el robot. Si la camara dejo de entregar, devuelve
    neutro: mantener el ultimo comando con el video colgado deja al robot
    girando para siempre sobre una orden vieja.
    """
    if not camara_viva():
        return dict(NEUTRO, fps=0.0, stale=True)
    return dict(_last_control, fps=round(_fps, 1), stale=False)


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def control_from_target(target: dict | None, frame_w: int, frame_h: int) -> dict:
    global _last_control
    if target is None:
        _last_control = {"turn": 0.0, "forward": 0.0, "has_target": False,
                         "track_id": None, "distance": None}
        return _last_control

    x1, y1, x2, y2 = target["box"]
    cx = (x1 + x2) / 2
    h_ratio = (y2 - y1) / frame_h

    turn = (cx - frame_w / 2) / (frame_w / 2)
    forward = (TARGET_HEIGHT_RATIO - h_ratio) / TARGET_HEIGHT_RATIO

    if abs(turn) < TURN_DEADZONE:
        turn = 0.0
    if abs(forward) < FORWARD_DEADZONE:
        forward = 0.0

    _last_control = {
        "turn": round(_clamp(turn), 3),
        "forward": round(_clamp(forward), 3),
        "has_target": True,
        "track_id": target["track_id"],
        "distance": round(h_ratio, 3),
    }
    return _last_control


def _color_por_id(i: int) -> tuple:
    rng = np.random.default_rng((i or 0) * 9781 + 7)
    return tuple(int(c) for c in rng.integers(70, 255, 3))


def _barra(img, x, y, valor, etiqueta):
    ancho, alto = 160, 12
    cv2.rectangle(img, (x, y), (x + ancho, y + alto), (60, 60, 60), -1)
    medio = x + ancho // 2
    largo = int(abs(valor) * (ancho // 2))
    if largo > 1:
        color = VERDE if abs(valor) < 0.6 else AMARILLO
        x1, x2 = (medio, medio + largo) if valor > 0 else (medio - largo, medio)
        cv2.rectangle(img, (x1, y), (x2, y + alto), color, -1)
    cv2.line(img, (medio, y), (medio, y + alto), (220, 220, 220), 1)
    cv2.putText(img, f"{etiqueta} {valor:+.2f}", (x + ancho + 10, y + alto),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)


def draw_overlay(frame, dets: list, target: dict | None, cmd: dict, fps: float = 0.0, seg: bool = False):
    h, w = frame.shape[:2]
    overlay = frame.copy()

    for d in dets:
        x1, y1, x2, y2 = (int(v) for v in d["box"])
        es_target = target is not None and d is target
        color = ROJO if es_target else _color_por_id(d["track_id"] or d["cls"])

        if d["mask"] is not None and len(d["mask"]):
            cv2.fillPoly(overlay, [d["mask"].astype(np.int32)], color)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3 if es_target else 2)
        tid = f"#{d['track_id']} " if d["track_id"] is not None else ""
        # Si la cara esta reconocida se muestra el nombre en lugar de "person":
        # el punto de todo esto es ver a quien tiene enfrente, no que hay uno.
        cara = (face_service.info_de(d["track_id"])
                if d["cls"] == PERSON_CLASS else None)
        if cara and cara["nombre"]:
            # El score va a la vista a proposito: es la unica forma de saber
            # si acerto raspando o con margen. Con 0.36 de umbral, 0.89 es
            # certeza y 0.40 es sospechoso.
            texto = f"{tid}{cara['nombre']} {cara['score']:.2f}"
        elif cara:
            # Cara vista pero de nadie conocido. Mostrar el mejor parecido
            # deja ver POR QUE no la reconocio.
            texto = f"{tid}desconocido ({cara['score']:.2f})"
        else:
            texto = f"{tid}{d['label']} {d['conf']:.2f}"
        cv2.rectangle(frame, (x1, y1 - 20), (x1 + 9 * len(texto), y1), color, -1)
        cv2.putText(frame, texto, (x1 + 3, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)

    if seg:
        frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

    cv2.line(frame, (w // 2, 0), (w // 2, h), GRIS, 1)

    if cmd["has_target"] and target is not None:
        x1, y1, x2, y2 = target["box"]
        cx = int((x1 + x2) / 2)
        cv2.line(frame, (cx, 0), (cx, h), ROJO, 1)
        cv2.arrowedLine(frame, (w // 2, h - 30), (cx, h - 30), ROJO, 2, tipLength=0.3)

    panel = frame.copy()
    cv2.rectangle(panel, (0, 0), (w, 92), (25, 25, 25), -1)
    frame = cv2.addWeighted(panel, 0.65, frame, 0.35, 0)

    estado = f"objetivo #{cmd['track_id']}" if cmd["has_target"] else "sin objetivo"
    cv2.putText(frame, f"{estado}   {len(dets)} detecciones   {fps:4.1f} fps",
                (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1)
    _barra(frame, 12, 36, cmd["turn"], "giro")
    _barra(frame, 12, 62, cmd["forward"], "avance")
    if cmd["distance"] is not None:
        cv2.putText(frame, f"alto caja {cmd['distance']:.2f}", (w - 170, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return frame


def process(frame, classes=None, seg=False, conf=0.4, fps=0.0, imgsz=480):
    h, w = frame.shape[:2]
    dets = track(frame, classes=classes, seg=seg, conf=conf, imgsz=imgsz)
    target = pick_target(dets)
    cmd = control_from_target(target, w, h)
    return draw_overlay(frame, dets, target, cmd, fps=fps, seg=seg)


_cfg = {"cam": 0, "seg": False, "all_classes": False, "conf": 0.4,
        "imgsz": 480, "det_hz": None}   # det_hz se llena abajo, con el env ya leido

ANCHO, ALTO = 640, 480
# Cadencia de la camara y de YOLO. Las dos por env para poder bajarlas sin
# tocar codigo, porque son la principal palanca de CPU que tiene esta maquina.
#
# Por que bajaron de 30/12 a 10/5: medido, el proceso del servidor estaba a
# ~420% de CPU EN REPOSO, sin que nadie le hablara, y el LLM comparte esos
# mismos nucleos. A 30 fps se capturaba, se dibujaba y se comprimia a JPEG
# treinta veces por segundo para un panel que nadie mira de cerca.
#
# 10 fps siguen viendose fluidos en el navegador, y 5 Hz de deteccion alcanzan
# de sobra para seguir a una persona: alguien caminando no se cruza el cuadro
# en 200 ms. Cuando YOLO se mude a la Raspberry esto se baja a 0 y el PC se
# olvida del tema.
#
# DETECCIONES_HZ va en Hz y no en "1 de cada N frames" a proposito: asi no
# cambia solo porque la camara entregue mas o menos rapido.
CAM_FPS = int(os.environ.get("JARVIS_CAM_FPS", "10"))
DETECCIONES_HZ = float(os.environ.get("JARVIS_DET_HZ", "5"))
_cfg["det_hz"] = DETECCIONES_HZ
# Sin frame nuevo por mas de esto -> el robot frena. Se DERIVA del ritmo y no
# es un numero fijo: 0.5s clavado suponia una camara rapida. En la Raspberry, a
# 4 fps son 250ms por cuadro, y cualquier hipo del driver pasaba por "camara
# muerta" y frenaba al robot sin que pasara nada. Cuatro cuadros de margen, y
# nunca menos de medio segundo.
def _stale_s() -> float:
    return max(0.5, 4.0 / max(CAM_FPS, 1))


REABRIR_S = 2.0        # segundos sin frame antes de reabrir /dev/video

# Cuantos estan mirando el MJPEG ahora mismo. Sirve para no dibujar ni
# comprimir para nadie: ver `_draw_loop`.
_mirones = 0
_mirones_lock = threading.Lock()

# --- frame crudo recien salido de la camara (lo escribe el grabber) ---
_raw = None
_raw_n = 0
_raw_t = 0.0
_raw_cond = threading.Condition()

# --- frame ya dibujado y comprimido (lo escribe el hilo de inferencia) ---
_frame_jpeg = None
_frame_n = 0
_cond = threading.Condition()

_grabber = None
_detector = None
_dibujante = None
_worker_err = None
_worker_lock = threading.Lock()
_fps = 0.0
# El stream MJPEG es un generador infinito. Sin una senal de apagado, uvicorn
# se queda esperando para siempre a que la request "termine" y el reinicio
# nunca ocurre: el worker viejo no muere, el nuevo no arranca y el server
# entero deja de aceptar conexiones.
_apagando = threading.Event()


def apagar() -> None:
    _apagando.set()
    with _cond:
        _cond.notify_all()
    with _raw_cond:
        _raw_cond.notify_all()


def configure(seg: bool | None = None, all_classes: bool | None = None,
              conf: float | None = None, imgsz: int | None = None,
              det_hz: float | None = None) -> dict:
    if seg is not None:
        _cfg["seg"] = seg
    if all_classes is not None:
        _cfg["all_classes"] = all_classes
    if conf is not None:
        _cfg["conf"] = conf
    if imgsz is not None:
        _cfg["imgsz"] = imgsz
    if det_hz is not None:
        # Acotado: 0 congela la vision y valores altos no compran nada porque
        # la camara no entrega mas rapido que CAM_FPS.
        _cfg["det_hz"] = max(0.5, min(float(det_hz), float(CAM_FPS)))
    return dict(_cfg)


def _abrir_camara():
    cap = cv2.VideoCapture(_cfg["cam"], cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    # BUFFERSIZE=1 es lo que impide que el driver acumule frames viejos. Sin
    # esto, cuando el consumidor se atrasa la cola del kernel se llena y
    # cap.read() devuelve rafagas instantaneas de frames rancios (de ahi los
    # "161 fps"), hasta que V4L2 se traba con select() timeout.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO)
    # Pedirselo al driver es un DESEO, no una orden: medido en esta webcam,
    # pidiendole 30, 15, 10 o 5 siempre contesta "30.0" y siempre entrega 15.
    # Se deja igual porque hay camaras que si lo respetan y ahi ahorra el
    # trabajo de decodificar cuadros que despues tiramos; el que garantiza el
    # ritmo es el freno por software del grabber.
    cap.set(cv2.CAP_PROP_FPS, CAM_FPS)
    return cap


def _grab_loop():
    """Unico dueno de /dev/video. No hace nada pesado: lee y publica.

    Que este hilo no tenga inferencia adentro es todo el punto. Mientras YOLO
    piensa, este sigue drenando la camara, asi que el FIFO nunca se acumula y
    el frame que ve la inferencia siempre es el mas reciente.
    """
    global _raw, _raw_n, _raw_t, _worker_err, _fps
    cap = None
    marcas = collections.deque(maxlen=40)
    periodo = 1.0 / max(CAM_FPS, 1)
    ultimo_frame = 0.0
    try:
        while True:
            # Apagar el modulo CIERRA la camara. Dejarla abierta y sin leer
            # era lo que la mataba: el driver sigue llenando buffers que
            # nadie saca, se queda sin ninguno libre y despues cada read()
            # se cuelga 10s en select(). Por eso "apagar y prender" no
            # arreglaba nada: el boton era justamente lo que la trababa.
            if not runtime.activo("vision"):
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.25)
                continue

            if cap is None:
                cap = _abrir_camara()
                if cap is None:
                    _worker_err = "No pude abrir /dev/video%d" % _cfg["cam"]
                    time.sleep(1.0)
                    continue
                _worker_err = None
                with _raw_cond:
                    _raw_t = time.time()   # gracia para no reabrir enseguida

            # Freno por software. Es lo unico que hace que JARVIS_CAM_FPS
            # signifique algo: sin esto el hilo lee tan rapido como la camara
            # entregue —15 fps acá, sin importar lo que se le pida— y bajar el
            # numero no cambiaba nada. Se duerme ANTES de leer, no despues, para
            # que el cuadro que se lee sea el mas nuevo posible; con
            # BUFFERSIZE=1 el driver ya descarto los viejos.
            espera = periodo - (time.time() - ultimo_frame)
            if espera > 0:
                time.sleep(espera)
            ultimo_frame = time.time()

            ok, frame = cap.read()
            if ok:
                # El fps se mide ACA y no en el dibujado. Antes salia de los
                # frames publicados como JPEG, y desde que el dibujado se
                # apaga cuando nadie mira, eso habria reportado 0 fps con la
                # camara andando perfectamente.
                ahora = time.time()
                marcas.append(ahora)
                if len(marcas) > 1:
                    span = marcas[-1] - marcas[0]
                    _fps = (len(marcas) - 1) / span if span > 0 else 0.0
                with _raw_cond:
                    _raw = frame
                    _raw_n += 1
                    _raw_t = ahora
                    _raw_cond.notify_all()
                continue

            # Se reabre por TIEMPO SIN FRAME, no por cantidad de fallos.
            # Contando fallos no servia: cuando V4L2 se traba cada read()
            # tarda 10s en fallar, asi que 40 fallos eran ~400s de video
            # congelado antes de siquiera intentar reabrir.
            with _raw_cond:
                sin_frame = time.time() - _raw_t
            if sin_frame > REABRIR_S:
                cap.release()
                cap = None
                time.sleep(0.3)
            else:
                time.sleep(0.02)
    finally:
        if cap is not None:
            cap.release()


# --- resultado de deteccion, compartido entre el detector y el dibujante ---
_det_state = {"dets": [], "target": None,
              "cmd": {"turn": 0.0, "forward": 0.0, "has_target": False,
                      "track_id": None, "distance": None}}
_det_lock = threading.Lock()


def _detect_loop():
    """YOLO a su propio ritmo, sin frenar la salida de video.

    Antes la deteccion vivia en el mismo loop que el dibujo, con
    DETECTAR_CADA para abaratarla: eso hacia que 1 de cada 3 frames costara
    el doble y la cadencia saliera a los saltos (33ms, 33ms, 60ms...). Aca el
    detector corre suelto y el dibujante usa siempre las ultimas cajas.
    """
    aplicar_hilos()
    visto = -1
    while True:
        # Se relee en cada vuelta: cambiar det_hz por la API tiene que hacer
        # efecto en el proximo cuadro, no en el proximo reinicio.
        periodo = 1.0 / max(_cfg["det_hz"] or DETECCIONES_HZ, 0.1)
        with _raw_cond:
            _raw_cond.wait_for(lambda: _raw_n != visto, timeout=1.0)
            if _raw_n == visto or _raw is None:
                continue
            visto = _raw_n
            frame = _raw.copy()

        t0 = time.time()
        h, w = frame.shape[:2]
        classes = None if _cfg["all_classes"] else [PERSON_CLASS]
        dets = track(frame, classes=classes, seg=_cfg["seg"],
                     conf=_cfg["conf"], imgsz=_cfg["imgsz"])
        target = pick_target(dets)
        cmd = control_from_target(target, w, h)

        # Ponerle nombre a las personas nuevas. Cuesta casi nada porque solo
        # corre cuando aparece un track sin identificar; con las mismas
        # personas en cuadro no hace ningun trabajo.
        try:
            personas = [d for d in dets if d["cls"] == PERSON_CLASS]
            if personas:
                face_service.identificar(frame, personas)
        except Exception:
            pass      # sin caras enroladas o sin modelos, la vision sigue igual

        with _det_lock:
            _det_state["dets"] = dets
            _det_state["target"] = target
            _det_state["cmd"] = cmd

        sobra = periodo - (time.time() - t0)
        if sobra > 0:
            time.sleep(sobra)


def _draw_loop():
    """Dibuja y comprime cada frame, PERO solo si alguien esta mirando.

    Dibujar el overlay y comprimir a JPEG es un costo constante que no depende
    de que pase en la escena, y hasta ahora se pagaba siempre: con la pestana
    cerrada, el robot solo, o el celular en el bolsillo, la maquina seguia
    generando diez imagenes por segundo para nadie. En este PC es molesto; en
    una Raspberry es una fraccion seria del presupuesto, y encima compite con
    la inferencia, que es lo unico que el robot necesita de verdad.

    La deteccion NO se apaga: el robot tiene que seguir viendo aunque nadie
    este mirando la pantalla. Lo que se apaga es la pantalla, no los ojos.
    """
    global _frame_jpeg, _frame_n
    visto = -1

    while True:
        if not _hay_mirones():
            # No basta con no dibujar: hay que consumir el contador de frames
            # igual, o al volver alguien se procesaria de golpe el atraso.
            with _raw_cond:
                _raw_cond.wait(timeout=0.5)
                visto = _raw_n
            continue
        with _raw_cond:
            _raw_cond.wait_for(lambda: _raw_n != visto, timeout=1.0)
            if _raw_n == visto or _raw is None:
                continue
            visto = _raw_n
            frame = _raw.copy()

        with _det_lock:
            dets = _det_state["dets"]
            target = _det_state["target"]
            cmd = _det_state["cmd"]

        frame = draw_overlay(frame, dets, target, cmd, fps=_fps, seg=_cfg["seg"])
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue

        with _cond:
            _frame_jpeg = buf.tobytes()
            _frame_n += 1
            _cond.notify_all()


def frame_crudo():
    """El ultimo cuadro sin dibujar. Lo usa el enrolamiento de caras: el
    overlay taparia justo lo que hay que medir."""
    with _raw_cond:
        return None if _raw is None else _raw.copy()


def camara_viva() -> bool:
    with _raw_cond:
        return _raw_t > 0 and (time.time() - _raw_t) < _stale_s()


def ensure_worker() -> None:
    global _grabber, _detector, _dibujante, _worker_err
    # Un solo hilo puede abrir /dev/video0. Sin este lock, dos requests
    # simultaneos arrancaban dos capture loops y el segundo fallaba.
    with _worker_lock:
        hilos = {"grabber": (_grabber, _grab_loop),
                 "detector": (_detector, _detect_loop),
                 "dibujante": (_dibujante, _draw_loop)}
        if all(h is not None and h.is_alive() for h, _ in hilos.values()):
            return
        _worker_err = None
        if _grabber is None or not _grabber.is_alive():
            _grabber = threading.Thread(target=_grab_loop, daemon=True)
            _grabber.start()
        if _detector is None or not _detector.is_alive():
            _detector = threading.Thread(target=_detect_loop, daemon=True)
            _detector.start()
        if _dibujante is None or not _dibujante.is_alive():
            _dibujante = threading.Thread(target=_draw_loop, daemon=True)
            _dibujante.start()
        time.sleep(1.5)
        if _worker_err:
            raise RuntimeError(_worker_err)


def _hay_mirones() -> bool:
    with _mirones_lock:
        return _mirones > 0


def mjpeg_stream():
    global _mirones
    ensure_worker()
    with _mirones_lock:
        _mirones += 1
    try:
        yield from _mjpeg()
    finally:
        # En finally y no al salir del while: el cliente se va cerrando el
        # socket, o sea con una excepcion, no por la condicion del bucle.
        with _mirones_lock:
            _mirones -= 1


def _mjpeg():
    ultimo = -1
    while not _apagando.is_set():
        with _cond:
            # Si el worker se demora no cortamos la conexion: reenviamos el
            # ultimo frame. Cortar dejaba el <img> congelado para siempre.
            _cond.wait_for(lambda: _frame_n != ultimo, timeout=2.0)
            ultimo = _frame_n
            jpeg = _frame_jpeg
        if jpeg is None:
            time.sleep(0.1)
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")


# COCO nombra en ingles. Se traducen las clases que aparecen en una pieza; el
# resto se dice en ingles, que es mejor que no nombrar la cosa.
ES = {
    "person": "persona", "chair": "silla", "couch": "sofa", "bed": "cama",
    "dining table": "mesa", "tv": "televisor", "laptop": "computadora",
    "mouse": "mouse", "keyboard": "teclado", "cell phone": "celular",
    "book": "libro", "clock": "reloj", "cup": "taza", "bottle": "botella",
    "bowl": "plato", "backpack": "mochila", "handbag": "bolso",
    "potted plant": "planta", "vase": "florero", "scissors": "tijeras",
    "remote": "control remoto", "teddy bear": "peluche", "dog": "perro",
    "cat": "gato", "refrigerator": "nevera", "microwave": "microondas",
    "sink": "lavaplatos", "toothbrush": "cepillo de dientes",
    "banana": "banano", "apple": "manzana", "orange": "naranja",
}

NUMEROS = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis"}


def _nombrar(label: str, n: int) -> str:
    palabra = ES.get(label, label)
    if n == 1:
        return f"{'una' if palabra.endswith('a') else 'un'} {palabra}"
    plural = palabra + ("es" if palabra[-1] not in "aeiou" else "s")
    return f"{NUMEROS.get(n, n)} {plural}"


def lo_que_veo(maximo: int = 5) -> dict:
    """Lo que la camara tiene enfrente ahora mismo, en palabras.

    Se arma cada vez que se pide, nunca se cachea: el punto es que sea lo
    ultimo, no lo que habia cuando alguien pregunto.
    """
    if not camara_viva():
        return {"viva": False, "texto": "", "objetos": {}}

    with _det_lock:
        dets = list(_det_state.get("dets") or [])

    # Ordenadas por tamaño: lo que ocupa mas cuadro es lo que tiene mas cerca.
    # A las personas conocidas se las nombra: para Russ no es lo mismo "una
    # persona" que "Jaime", y es la diferencia entre describir y reconocer.
    cuenta, orden, nombres = {}, {}, []
    for d in sorted(dets, key=lambda x: -x["area"]):
        etiqueta = d["label"]
        if d["cls"] == PERSON_CLASS:
            quien = face_service.nombre_de(d.get("track_id"))
            if quien:
                if quien not in nombres:
                    nombres.append(quien)
                continue
        cuenta[etiqueta] = cuenta.get(etiqueta, 0) + 1
        orden.setdefault(etiqueta, len(orden))

    labels = sorted(cuenta, key=lambda l: orden[l])[:maximo]
    piezas = nombres + [_nombrar(l, cuenta[l]) for l in labels]
    if not piezas:
        texto = "nada que reconozca"
    elif len(piezas) == 1:
        texto = piezas[0]
    else:
        texto = ", ".join(piezas[:-1]) + " y " + piezas[-1]

    return {"viva": True, "texto": texto, "objetos": cuenta,
            "personas": nombres}
