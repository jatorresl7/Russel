"""El cache de pensamientos: buscar el arranque que corresponde y precargarlo.

Es RAG, pero sobre razonamiento y no sobre datos. La diferencia con cachear la
respuesta importa: la respuesta depende de lo que la camara ve AHORA y de lo
que recuerda AHORA, asi que congelarla da respuestas viejas con conviccion. El
ENFOQUE —"me estan preguntando por mis limites, conviene nombrar cuales son"—
no depende de nada de eso, y por eso si se recicla.

El umbral es alto a proposito. Con 0.845, que es el de las memorias, "que ves"
y "que viste" caen en el mismo pensamiento y quieren cosas distintas. Un fallo
aca no es una memoria de mas en el prompt: es precargarle a Russ un
razonamiento que no corresponde y que va a seguir como si fuera propio.
"""
import hashlib
import json
from datetime import datetime

from app.db import SessionLocal, Pensamiento
from app.services import embedding_service as emb
from app.services.pensamientos_semilla import SEMILLA

# Mas alto que UMBRAL de memorias (0.845) por lo dicho arriba. Preferimos
# perder un acierto —y que piense normal, que ya funciona— antes que meterle
# el pensamiento equivocado.
UMBRAL = float(__import__("os").environ.get("JARVIS_PENS_UMBRAL", "0.90"))


_sembrado = False


def _huella() -> str:
    """Huella del catalogo + el modelo que lo vectorizo.

    El texto vive en el repo y la tabla es una copia; sin esto, editar un
    pensamiento y olvidarse de re-sembrar deja la base sirviendo la version
    vieja EN SILENCIO, que es la peor forma de fallar. El modelo entra en la
    huella porque los vectores son suyos: cambiarlo invalida los 120 aunque el
    texto no se haya tocado.
    """
    crudo = json.dumps([SEMILLA, emb.MODELO], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(crudo.encode()).hexdigest()[:16]


def asegurar_semilla() -> None:
    """Siembra si hace falta, y re-siembra sola si el catalogo cambio.

    No se hace al crear las tablas porque ahi el modulo `embed` todavia puede
    estar apagado y sin el no hay vectores. Aca se intenta en el primer turno,
    que es cuando el sistema ya esta en marcha de verdad.
    """
    global _sembrado
    if _sembrado or not emb.disponible():
        return
    try:
        huella = _huella()
        db = SessionLocal()
        try:
            fila = db.query(Pensamiento).first()
            al_dia = fila is not None and (fila.modelo or "").endswith(huella)
        finally:
            db.close()
        if not al_dia:
            sembrar(forzar=True)
    except Exception:
        return          # se reintenta el turno que viene
    _sembrado = True


def buscar(consulta: str, umbral: float = UMBRAL) -> dict | None:
    """El pensamiento mas parecido, o None si ninguno llega al umbral.

    None no es un error: significa "pensa vos", que es el camino que ya
    existia. El cache acelera cuando acierta y no estorba cuando no.
    """
    if not consulta.strip() or not emb.disponible():
        return None
    asegurar_semilla()
    vector = emb.de_consulta(consulta)

    db = SessionLocal()
    try:
        sim = (1 - Pensamiento.vector.cosine_distance(vector)).label("sim")
        fila = (db.query(Pensamiento, sim)
                .filter(Pensamiento.vigente.is_(True))
                .order_by(Pensamiento.vector.cosine_distance(vector))
                .first())
        if not fila or fila[1] is None or float(fila[1]) < umbral:
            return None
        p, s = fila
        db.query(Pensamiento).filter(Pensamiento.id == p.id).update(
            {Pensamiento.usos: Pensamiento.usos + 1,
             Pensamiento.ultimo_uso: datetime.utcnow()},
            synchronize_session=False)
        db.commit()
        return {"id": p.id, "texto": p.texto, "disparador": p.disparador,
                "sim": round(float(s), 3)}
    finally:
        db.close()


def sembrar(forzar: bool = False) -> dict:
    """Carga el catalogo escrito a mano. Idempotente salvo `forzar`.

    Se re-siembra entero y no fila por fila: el catalogo es codigo, y si cambio
    el texto de un pensamiento quiero el nuevo, no los dos.
    """
    if not emb.disponible():
        return {"sembrados": 0, "motivo": "el modulo embed esta apagado"}

    db = SessionLocal()
    try:
        hay = db.query(Pensamiento).count()
        if hay and not forzar:
            return {"sembrados": 0, "ya_habia": hay}
        db.query(Pensamiento).delete()
        # Una fila por FRASE, no por pensamiento: varias frases apuntando al
        # mismo texto. Ver la nota de `pensamientos_semilla` — juntarlas en un
        # solo string promedia los vectores y deja el margen en una milesima.
        pares = [(d, texto.strip()) for disparadores, texto in SEMILLA
                 for d in disparadores]
        vectores = emb.de_memorias([d for d, _ in pares])
        for (disparador, texto), v in zip(pares, vectores):
            db.add(Pensamiento(disparador=disparador, texto=texto,
                               vector=v, modelo=f"{emb.MODELO}#{_huella()}"))
        db.commit()
        return {"pensamientos": len(SEMILLA), "sembrados": len(pares),
                "reemplazo": hay}
    finally:
        db.close()


def estado() -> dict:
    db = SessionLocal()
    try:
        filas = (db.query(Pensamiento)
                 .order_by(Pensamiento.usos.desc()).limit(40).all())
        return {"total": db.query(Pensamiento).count(), "umbral": UMBRAL,
                "pensamientos": [{"id": p.id, "disparador": p.disparador,
                                  "usos": p.usos or 0,
                                  "texto": p.texto} for p in filas]}
    finally:
        db.close()
