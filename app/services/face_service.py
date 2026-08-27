"""Reconocer a quien tiene enfrente. Sin entrenar nada.

No se entrena un modelo por persona: SFace ya viene entrenado para mapear
cualquier cara a un vector de 128 numeros donde las caras de la misma persona
caen cerca. Enrolar a alguien es guardar unos cuantos de esos vectores;
reconocerlo es medir distancia coseno contra los guardados. Agregar una
persona nueva no toca los pesos de nada.

Las dos piezas ya vienen en OpenCV, no hay dependencia nueva:
  YuNet  -> encuentra las caras en el cuadro (228 KB)
  SFace  -> convierte cada cara en su vector (37 MB)

El costo se mantiene bajo por como se usa, no por lo rapido que sea: ByteTrack
ya asigna un track_id estable a cada persona, asi que se reconoce UNA vez
cuando aparece un track nuevo y el nombre se le pega al id. Mientras no se
pierda de vista, no se vuelve a calcular.
"""
import os
import threading
import time

import cv2
import numpy as np

from app.db import Face, SessionLocal

# Los recortes de cada enrolamiento se guardan en disco. El vector solo no
# sirve para revisar nada: si enrolo mal (una oreja, un borrón, la persona
# equivocada) no hay forma de darse cuenta mirando 128 numeros.
FOTOS_DIR = os.path.expanduser("~/.cache/jarvis/caras")

YUNET = os.path.expanduser("~/.cache/opencv_zoo/yunet.onnx")
SFACE = os.path.expanduser("~/.cache/opencv_zoo/sface.onnx")

# Umbral de coseno de la propia gente de SFace: por encima es la misma persona.
UMBRAL = 0.363
MIN_CONF_CARA = 0.8      # confianza minima del detector para molestarse
OLVIDO = 20.0            # segundos sin ver un track antes de soltar su nombre
REINTENTO_S = 1.5        # cada cuanto se reintenta un track que NO se reconocio

_detector = None
_embedder = None
_lock = threading.Lock()

_conocidos: dict[str, list] = {}      # nombre -> [vector, ...]
_por_track: dict[int, dict] = {}      # track_id -> {"nombre", "score", "visto", "intentado"}
_conocidos_leidos = False             # ya se trajo la DB a memoria al menos una vez


def _cargar():
    global _detector, _embedder
    if _detector is None:
        for ruta in (YUNET, SFACE):
            if not os.path.isfile(ruta):
                raise RuntimeError(f"falta el modelo {ruta}")
        _detector = cv2.FaceDetectorYN.create(YUNET, "", (320, 320),
                                              score_threshold=MIN_CONF_CARA)
        _embedder = cv2.FaceRecognizerSF.create(SFACE, "")
        recargar()
    return _detector, _embedder


def recargar() -> dict:
    """Trae las caras conocidas de la DB a memoria."""
    global _conocidos
    db = SessionLocal()
    try:
        nuevo = {}
        for f in db.query(Face).all():
            nuevo.setdefault(f.nombre, []).append(np.array(f.embedding, dtype=np.float32))
        _conocidos = nuevo
    finally:
        db.close()
    global _conocidos_leidos
    _conocidos_leidos = True
    return {"personas": {n: len(v) for n, v in _conocidos.items()}}


def _asegurar_conocidos() -> None:
    """Trae las caras de la DB la primera vez que hacen falta.

    No alcanza con hacerlo en `_cargar()`, que es donde se cargan los modelos:
    a `_cargar()` solo se llega desde `_caras()`, y `identificar()` corta antes
    si `_conocidos` esta vacio. O sea que despues de cada reinicio del server
    -y con --reload eso es cada vez que se guarda un archivo- el reconocimiento
    quedaba muerto: la DB tenia los vectores, la memoria no, y nada los iba a
    traer hasta que alguien enrolara u olvidara a alguien. Desde afuera se veia
    como "la vision esta apagada": todo el mundo etiquetado 'person'.
    """
    if not _conocidos_leidos:
        recargar()


def _caras(frame) -> list:
    """Devuelve [(caja, vector)] de cada cara del cuadro."""
    det, emb = _cargar()
    h, w = frame.shape[:2]
    det.setInputSize((w, h))
    _, caras = det.detect(frame)
    if caras is None:
        return []
    out = []
    for cara in caras:
        alineada = emb.alignCrop(frame, cara)
        vector = emb.feature(alineada).flatten().astype(np.float32)
        x, y, bw, bh = cara[:4]
        out.append(((float(x), float(y), float(bw), float(bh)), vector))
    return out


def _mejor(vector) -> tuple:
    """Contra quien se parece mas, y cuanto. Se queda con el MAXIMO de las
    fotos de cada persona, no con el promedio: alcanza con parecerse a una
    de las vistas guardadas."""
    mejor_nombre, mejor_score = None, 0.0
    for nombre, vistas in _conocidos.items():
        for v in vistas:
            score = float(np.dot(vector, v) /
                          (np.linalg.norm(vector) * np.linalg.norm(v) + 1e-9))
            if score > mejor_score:
                mejor_nombre, mejor_score = nombre, score
    return (mejor_nombre, mejor_score) if mejor_score >= UMBRAL else (None, mejor_score)


def _reintentar(info: dict | None, ahora: float) -> bool:
    """Si a este track hay que (volver a) ponerle nombre.

    Un `nombre=None` NO se puede dar por definitivo. Alcanza UN cuadro malo
    -de perfil, movido, a contraluz- justo cuando aparece el track para que la
    persona quede etiquetada 'person' todo lo que dure ese track, que mientras
    siga en cuadro es para siempre: `visto` se refresca en cada vuelta, asi que
    OLVIDO nunca llega. De ahi el "no me reconoce a la primera" que se arreglaba
    solo al salir y volver a entrar en cuadro, que es cuando el tracker le da un
    id nuevo y se vuelve a intentar.

    El acierto si es definitivo: reidentificar a alguien ya reconocido gasta CPU
    y hace parpadear el nombre entre cuadro y cuadro.
    """
    if info is None:
        return True
    if info["nombre"] is not None:
        return False
    return ahora - info.get("intentado", 0.0) >= REINTENTO_S


def identificar(frame, personas: list) -> dict:
    """Le pone nombre a los tracks de persona que todavia no lo tengan.

    `personas` son las detecciones de YOLO de clase persona, con su track_id.
    Solo se calculan las caras si hay algun track sin identificar: si ya se
    sabe quien es cada uno, esta funcion no hace nada.
    """
    _asegurar_conocidos()
    ahora = time.time()
    with _lock:
        for tid, info in list(_por_track.items()):
            if ahora - info["visto"] > OLVIDO:
                del _por_track[tid]

        pendientes = [p for p in personas
                      if p.get("track_id") is not None
                      and _reintentar(_por_track.get(p["track_id"]), ahora)]
        for p in personas:
            tid = p.get("track_id")
            if tid in _por_track:
                _por_track[tid]["visto"] = ahora

        if not pendientes or not _conocidos:
            return dict(_por_track)

    for caja, vector in _caras(frame):
        fx, fy, fw, fh = caja
        cx, cy = fx + fw / 2, fy + fh / 2
        # La cara se le asigna al track cuya caja la contiene.
        for p in pendientes:
            x1, y1, x2, y2 = p["box"]
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                nombre, score = _mejor(vector)   # score = mejor parecido,
                                                 # haya reconocido o no
                with _lock:
                    _por_track[p["track_id"]] = {
                        "nombre": nombre, "score": round(score, 3),
                        "visto": ahora, "intentado": ahora}
                break

    with _lock:
        return dict(_por_track)


def nombre_de(track_id) -> str | None:
    with _lock:
        info = _por_track.get(track_id)
    return info["nombre"] if info else None


def info_de(track_id) -> dict | None:
    """Nombre Y score. El score importa tanto como el nombre: sin el no hay
    forma de distinguir un acierto claro de uno que paso raspando."""
    with _lock:
        info = _por_track.get(track_id)
    return dict(info) if info else None


def enrolar(frame, nombre: str) -> dict:
    """Guarda una cara mas para `nombre`. Falla si hay 0 o mas de 1 cara:
    con dos personas en el cuadro no hay forma de saber cual enrolar."""
    caras = _caras(frame)
    if len(caras) != 1:
        return {"ok": False, "motivo": f"se ven {len(caras)} caras, tiene que ser 1"}

    caja, vector = caras[0]
    db = SessionLocal()
    try:
        fila = Face(nombre=nombre, embedding=vector.tolist())
        db.add(fila)
        db.commit()
        fid = fila.id
    finally:
        db.close()

    # El mismo recorte alineado que se midio, no el cuadro entero: asi lo que
    # ves es exactamente lo que se convirtio en el vector.
    _, emb = _cargar()
    det, _ = _cargar()
    ruta = os.path.join(FOTOS_DIR, nombre)
    os.makedirs(ruta, exist_ok=True)
    h, w = frame.shape[:2]
    det.setInputSize((w, h))
    _, crudas = det.detect(frame)
    if crudas is not None and len(crudas):
        cv2.imwrite(os.path.join(ruta, f"{fid}.jpg"),
                    emb.alignCrop(frame, crudas[0]))

    recargar()
    return {"ok": True, "nombre": nombre, "id": fid,
            "fotos": len(_conocidos.get(nombre, []))}


def fotos_de(nombre: str) -> list:
    ruta = os.path.join(FOTOS_DIR, nombre)
    if not os.path.isdir(ruta):
        return []
    return sorted(os.path.join(ruta, f) for f in os.listdir(ruta)
                  if f.endswith(".jpg"))


def olvidar(nombre: str) -> dict:
    db = SessionLocal()
    try:
        n = db.query(Face).filter(Face.nombre == nombre).delete()
        db.commit()
    finally:
        db.close()
    import shutil
    shutil.rmtree(os.path.join(FOTOS_DIR, nombre), ignore_errors=True)
    recargar()
    return {"ok": True, "borradas": n}


def estado() -> dict:
    # Sin esto la galeria muestra "ninguna cara enrolada" con la DB llena,
    # porque `_conocidos` todavia no se leyo. Ver `_asegurar_conocidos`.
    _asegurar_conocidos()
    with _lock:
        tracks = {str(k): {"nombre": v["nombre"], "score": v["score"]}
                  for k, v in _por_track.items()}
    return {"conocidos": {n: len(v) for n, v in _conocidos.items()},
            "tracks": tracks, "umbral": UMBRAL}


def enrolar_desde_camara(nombre: str, fotos: int = 5, espera: float = 0.7) -> dict:
    """Toma varias fotos de la camara en vivo y las enrola.

    Varias y no una: una sola vista no cubre los cambios de luz ni los angulos,
    y despues no te reconoce si girás la cabeza. Entre foto y foto hay una
    pausa para que te muevas un poco -- la variedad es justamente el punto.
    """
    from app.services import vision_service

    vision_service.ensure_worker()
    guardadas, fallos = 0, []
    for i in range(fotos):
        frame = vision_service.frame_crudo()
        if frame is None:
            fallos.append("la camara no esta entregando cuadros")
            break
        r = enrolar(frame, nombre)
        if r["ok"]:
            guardadas += 1
        else:
            fallos.append(r["motivo"])
        if i < fotos - 1:
            time.sleep(espera)

    return {"ok": guardadas > 0, "nombre": nombre, "guardadas": guardadas,
            "total_fotos": len(_conocidos.get(nombre, [])), "fallos": fallos}
