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
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()   # sin esto, JARVIS_PENS_UMBRAL en el .env no se veia nunca

from app.db import SessionLocal, Pensamiento
from app.services import embedding_service as emb
from app.services.pensamientos_semilla import SEMILLA

# Mas alto que UMBRAL de memorias (0.845) por lo dicho arriba. Preferimos
# perder un acierto —y que piense normal, que ya funciona— antes que meterle
# el pensamiento equivocado.
# Poner 2 (o cualquier valor > 1) apaga el cache: ninguna similitud lo alcanza
# y todos los turnos vuelven a pensar normal.
UMBRAL = float(os.environ.get("JARVIS_PENS_UMBRAL", "0.90"))

# MARGEN MINIMO contra el mejor de OTRO pensamiento. Sin esto el umbral solo no
# alcanza, y esta medido: las paráfrasis correctas caen entre 0.870 y 0.935, y
# los matches equivocados entre 0.822 y 0.922. Se solapan enteros, asi que no
# existe un umbral que separe — subirlo a 0.93 deja pasar 1 de 10 aciertos y
# mata el cache.
#
# Lo que si separa es la FORMA de la vecindad. Visto en vivo: "me voy a
# enloquecer" dio 0.922 / 0.911 / 0.909 —plano, no se parece a nada en
# particular, solo cayó cerca de la familia "me voy a ..."— y le precargó el
# pensamiento de hablar de un lugar, del que salio un "¿que te parece el lugar
# donde estas?" que no venia a cuento. Una paráfrasis de verdad tiene escalon:
# "me voy a dormir ya" da 0.935 y el siguiente distinto queda 0.052 abajo.
#
# Con 0.90 + 0.015 el caso que rompio deja de dispararse y no queda ningun
# falso positivo en el set de prueba, a costa de un acierto. Es el intercambio
# correcto: perder un acierto cuesta LATENCIA —piensa normal, que ya funciona—
# y un falso positivo cuesta COHERENCIA, que es lo unico que no se recupera.
MARGEN = float(os.environ.get("JARVIS_PENS_MARGEN", "0.015"))


_sembrado = False


def _catalogo() -> tuple[dict, list]:
    """`({disparador: texto}, choques)`. Una fila por FRASE, no por pensamiento:
    varias frases apuntando al mismo texto. Juntarlas en un solo string promedia
    sus vectores y deja el margen entre pensamientos en una milesima.

    Un disparador solo puede llevar a UN pensamiento —es una fila con un vector—
    asi que si dos pensamientos declaran la misma frase, gana el ultimo. Eso es
    razonable como regla pero pesimo en silencio: quien agrega un pensamiento
    nuevo puede estar tapando uno viejo sin enterarse. Por eso los choques se
    devuelven y salen en el resultado de `sembrar()`.
    """
    catalogo, choques = {}, []
    for disparadores, texto in SEMILLA:
        for d in disparadores:
            if d in catalogo and catalogo[d] != texto.strip():
                choques.append(d)
            catalogo[d] = texto.strip()
    return catalogo, choques


def asegurar_semilla() -> None:
    """Pone la tabla al dia. Barato de llamar: si no cambio nada, no hace nada.

    Se intenta en el primer turno y no al crear las tablas porque ahi el modulo
    `embed` todavia puede estar apagado, y sin el no hay vectores.
    """
    global _sembrado
    if _sembrado or not emb.disponible():
        return
    try:
        r = sembrar()
        if r.get("motivo"):
            return                  # embed apagado: se reintenta el turno que viene
    except Exception:
        return                      # idem con cualquier otro fallo
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
        # Se piden varias y no una: hace falta el mejor de OTRO pensamiento
        # para medir el margen. 25 alcanza — los disparadores de un mismo
        # pensamiento son 6 como mucho, asi que siempre hay otro adentro.
        filas = (db.query(Pensamiento, sim)
                 .filter(Pensamiento.vigente.is_(True))
                 .order_by(Pensamiento.vector.cosine_distance(vector))
                 .limit(25).all())
        if not filas or filas[0][1] is None or float(filas[0][1]) < umbral:
            return None
        p, s = filas[0]
        rival = next((float(v) for q, v in filas[1:] if q.texto != p.texto), 0.0)
        if float(s) - rival < MARGEN:
            return None          # vecindad plana: no se parece, solo esta cerca
        margen = float(s) - rival
        db.query(Pensamiento).filter(Pensamiento.id == p.id).update(
            {Pensamiento.usos: Pensamiento.usos + 1,
             Pensamiento.ultimo_uso: datetime.utcnow()},
            synchronize_session=False)
        db.commit()
        return {"id": p.id, "texto": p.texto, "disparador": p.disparador,
                "sim": round(float(s), 3), "margen": round(margen, 3)}
    finally:
        db.close()


def sembrar(forzar: bool = False) -> dict:
    """Siembra INCREMENTAL: solo toca lo que cambio.

    La version anterior borraba la tabla entera y re-vectorizaba las 292 filas
    cada vez que la huella del catalogo no coincidia — y la huella era un hash
    de SEMILLA entera, asi que corregir una coma en un pensamiento costaba 292
    embeddings. Con el catalogo creciendo eso pasa de molesto a inaceptable.

    Ahora se compara fila por fila:
      - disparador nuevo            -> se vectoriza y se inserta
      - texto cambiado              -> se actualiza (el vector NO, sale del
                                       disparador y el disparador no cambio)
      - el modelo de embeddings     -> se re-vectoriza esa fila
        de la fila no es el actual
      - disparador que ya no esta   -> se borra
      - todo igual                  -> no se toca, y esto es el caso normal

    El vector sale del `disparador`, no del `texto`: por eso cambiar la
    redaccion de un pensamiento no obliga a recalcular nada. Solo cambiar la
    frase que lo dispara, o el modelo que la vectorizo.

    `forzar` re-vectoriza todo aunque coincida. Es la salida para cuando se
    sospecha que la tabla quedo inconsistente.
    """
    if not emb.disponible():
        return {"sembrados": 0, "motivo": "el modulo embed esta apagado"}

    catalogo, choques = _catalogo()
    db = SessionLocal()
    try:
        filas = {p.disparador: p for p in db.query(Pensamiento).all()}

        sobran = [p for d, p in filas.items() if d not in catalogo]
        for p in sobran:
            db.delete(p)

        nuevos, revectorizar, retocados = [], [], 0
        for disparador, texto in catalogo.items():
            fila = filas.get(disparador)
            if fila is None:
                nuevos.append(disparador)
            elif forzar or fila.modelo != emb.MODELO or fila.vector is None:
                revectorizar.append(disparador)
                if fila.texto != texto:
                    fila.texto = texto
            elif fila.texto != texto:
                fila.texto = texto          # sin tocar el vector
                retocados += 1

        # Un solo viaje al embebedor para todo lo que haga falta: el costo por
        # llamada pesa mas que el numero de frases.
        pendientes = nuevos + revectorizar
        if pendientes:
            vectores = emb.de_memorias(pendientes)
            for disparador, v in zip(pendientes, vectores):
                fila = filas.get(disparador)
                if fila is None:
                    db.add(Pensamiento(disparador=disparador,
                                       texto=catalogo[disparador],
                                       vector=v, modelo=emb.MODELO))
                else:
                    fila.vector = v
                    fila.modelo = emb.MODELO

        db.commit()
        return {"total": len(catalogo), "nuevos": len(nuevos),
                "revectorizados": len(revectorizar), "retocados": retocados,
                "borrados": len(sobran), "modelo": emb.MODELO,
                "sin_cambios": len(catalogo) - len(pendientes) - retocados,
                "choques": choques}
    finally:
        db.close()


def estado() -> dict:
    db = SessionLocal()
    try:
        filas = (db.query(Pensamiento)
                 .order_by(Pensamiento.usos.desc()).limit(40).all())
        return {"total": db.query(Pensamiento).count(), "umbral": UMBRAL,
                "margen": MARGEN,
                "pensamientos": [{"id": p.id, "disparador": p.disparador,
                                  "usos": p.usos or 0,
                                  "texto": p.texto} for p in filas]}
    finally:
        db.close()
