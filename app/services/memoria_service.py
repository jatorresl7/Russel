"""La memoria de Russ: que guarda, como lo encuentra y como se consolida.

Dos formas de escribir, a proposito:

  explicito    Russ llama a la tool `recordar` porque le parecio que valia la
               pena. Cuesta solo cuando se usa, y lo que queda es lo que a EL
               le importo, que es mas interesante que lo que le importaria a un
               extractor generico.

  consolidado  Un trabajo de fondo relee `conversations` y saca lo que quedo
               implicito. Corre SOLO con la CPU libre, asi que no le suma un
               milisegundo a ningun turno.

Una sola forma de leer: busqueda por similitud, y lo que sale entra en el
mensaje volatil del prompt (nunca en el `system`, que tiene que quedar fijo
para que llama.cpp reuse el KV cache).
"""
import threading
import time
from datetime import datetime

from sqlalchemy import func, or_

from app.core import runtime
from app.db import SessionLocal, Memoria, Marcador, Conversation
from app.services import embedding_service as emb

TIPOS = ("hecho", "episodio")
FUENTES = ("explicito", "consolidado")

# e5 comprime las similitudes: medido en este proyecto, una memoria que responde
# a la consulta da ~0.88 y una sin ninguna relacion da ~0.79. O sea que el
# umbral util NO esta cerca de 0.5 sino pegado arriba, y mover esto dos
# centesimas cambia bastante que entra y que no.
UMBRAL = 0.845
TRAER = 4                 # cuantas memorias entran en el prompt como maximo

# Dos memorias que se parecen mas que esto son la misma cosa dicha distinto.
# Mas alto que UMBRAL porque acá no se trata de "viene al caso" sino de "ya lo
# tengo": si no, la consolidacion llena la tabla de variantes de un mismo hecho.
UMBRAL_DUPLICADO = 0.93

CLAVE_MARCA = "consolidacion_hasta"

_lock = threading.Lock()
_estado = {"consolidando": False, "ultima_consolidacion": None,
           "consolidadas": 0, "error": None}


# ── Escritura ───────────────────────────────────────────────────────────────

def guardar(texto: str, tipo: str = "hecho", fuente: str = "explicito",
            conversation_id: int | None = None, vigente: bool = True) -> dict:
    """Guarda una memoria. Devuelve `{guardada: False, motivo: ...}` cuando no
    valia la pena guardarla — que es un resultado normal, no un error.

    `vigente=False` la deja guardada pero fuera de `buscar()`: existe, se ve en
    la vista de conocimiento, y no la va a usar hasta que alguien la apruebe.
    Es como entra todo lo que produce la consolidacion.

    Por que: extraer datos de un dialogo es lo que peor le sale a un modelo de
    4B. Medido aca, sobre "mi hermana Ana vive en Cali" + "yo trabajo en Aixa"
    saco "Ana trabaja en Aixa" — se equivoco de persona. Insistir con el prompt
    mejoro el ruido pero no la atribucion. Una memoria mal atribuida es peor que
    ninguna, porque despues se recupera con toda confianza; asi que lo que sale
    de ahi espera aprobacion en vez de entrar directo."""
    texto = (texto or "").strip()
    if not texto:
        return {"guardada": False, "motivo": "vacio"}
    if tipo not in TIPOS:
        tipo = "hecho"
    if not emb.disponible():
        return {"guardada": False, "motivo": "el modulo embed esta apagado"}

    vector = emb.de_memoria(texto)

    db = SessionLocal()
    try:
        # No guardar lo que ya sabe. Es la unica defensa contra que la
        # consolidacion repita el mismo hecho una vez por conversacion.
        parecida = (db.query(Memoria, (1 - Memoria.vector.cosine_distance(vector)).label("sim"))
                    .order_by(Memoria.vector.cosine_distance(vector))
                    .limit(1).first())
        if parecida and parecida[1] is not None and parecida[1] >= UMBRAL_DUPLICADO:
            return {"guardada": False, "motivo": "ya lo sabía",
                    "parecida": parecida[0].texto, "sim": round(float(parecida[1]), 3)}

        m = Memoria(texto=texto, tipo=tipo, fuente=fuente, vector=vector,
                    modelo=emb.MODELO, conversation_id=conversation_id,
                    vigente=vigente)
        db.add(m)
        db.commit()
        db.refresh(m)
        return {"guardada": True, "id": m.id, "texto": m.texto, "tipo": m.tipo}
    finally:
        db.close()


def editar(id_: int, texto: str) -> dict:
    """Cambiar el texto obliga a recalcular el vector: si no, la memoria dice
    una cosa y se encuentra por otra."""
    db = SessionLocal()
    try:
        m = db.get(Memoria, id_)
        if not m:
            return {"ok": False, "motivo": "no existe"}
        m.texto = texto.strip()
        if emb.disponible():
            m.vector = emb.de_memoria(m.texto)
            m.modelo = emb.MODELO
        db.commit()
        return {"ok": True, "id": m.id}
    finally:
        db.close()


def aprobar(id_: int, vigente: bool = True) -> dict:
    """Deja que Russ use una memoria, o se la saca sin borrarla."""
    db = SessionLocal()
    try:
        m = db.get(Memoria, id_)
        if not m:
            return {"ok": False, "motivo": "no existe"}
        m.vigente = bool(vigente)
        db.commit()
        return {"ok": True, "id": m.id, "vigente": m.vigente}
    finally:
        db.close()


def olvidar(id_: int) -> dict:
    """Borra de verdad. Un `vigente=False` dejaria el texto en la DB, y para
    algo que se llama olvidar eso es mentir."""
    db = SessionLocal()
    try:
        n = db.query(Memoria).filter(Memoria.id == id_).delete()
        db.commit()
        return {"ok": bool(n)}
    finally:
        db.close()


# ── Lectura ─────────────────────────────────────────────────────────────────

def buscar(consulta: str, k: int = TRAER, umbral: float = UMBRAL) -> list[dict]:
    """Las memorias que vienen al caso, de la mas parecida a la menos.

    Marca las que devuelve como usadas: sirve para ver despues que memorias
    estan trabajando de verdad y cuales nunca sirvieron para nada.
    """
    if not consulta.strip() or not emb.disponible():
        return []
    vector = emb.de_consulta(consulta)

    db = SessionLocal()
    try:
        sim = (1 - Memoria.vector.cosine_distance(vector)).label("sim")
        filas = (db.query(Memoria, sim)
                 .filter(Memoria.vigente.is_(True))
                 .order_by(Memoria.vector.cosine_distance(vector))
                 .limit(k).all())
        salida, ids = [], []
        for m, s in filas:
            if s is None or float(s) < umbral:
                continue
            ids.append(m.id)
            salida.append({"id": m.id, "texto": m.texto, "tipo": m.tipo,
                           "fuente": m.fuente, "sim": round(float(s), 3)})
        if ids:
            (db.query(Memoria).filter(Memoria.id.in_(ids))
             .update({Memoria.usos: Memoria.usos + 1,
                      Memoria.ultimo_uso: datetime.utcnow()},
                     synchronize_session=False))
            db.commit()
        return salida
    finally:
        db.close()


def listar(q: str = "", tipo: str = "", fuente: str = "",
           page: int = 0, size: int = 50) -> dict:
    """Para la vista de conocimiento. Sin vectores: son 384 numeros por fila
    que el navegador no va a mirar nunca."""
    db = SessionLocal()
    try:
        query = db.query(Memoria)
        if q:
            query = query.filter(Memoria.texto.ilike(f"%{q}%"))
        if tipo:
            query = query.filter(Memoria.tipo == tipo)
        if fuente:
            query = query.filter(Memoria.fuente == fuente)
        total = query.count()
        filas = (query.order_by(Memoria.created_at.desc())
                 .offset(page * size).limit(size).all())
        return {"items": [_dto(m) for m in filas], "total": total,
                "page": page, "size": size}
    finally:
        db.close()


def _dto(m: Memoria) -> dict:
    return {"id": m.id, "texto": m.texto, "tipo": m.tipo, "fuente": m.fuente,
            "usos": m.usos or 0, "vigente": bool(m.vigente),
            "modelo": m.modelo,
            "ultimo_uso": m.ultimo_uso.isoformat() if m.ultimo_uso else None,
            "created_at": m.created_at.isoformat() if m.created_at else None}


# ── Consolidacion diferida ──────────────────────────────────────────────────

LOTE = 16          # turnos por vuelta. Mas no entra comodo en 4096 de contexto.

# Redactado despues de ver lo que producia la primera version. Con solo pedir
# "los hechos que van a seguir siendo ciertos manana", Qwen3-4B devolvia cosas
# como "El usuario necesita algo", "El usuario tiene un problema", "El usuario
# esta interactuando con un robot" y "El robot vive en una sala con una camara":
# parafrasis del momento y descripciones del propio sistema, no conocimiento.
# Un modelo chico necesita que le digan que NO cuenta, con ejemplos, y que le
# den permiso explicito de no encontrar nada — si no, siempre encuentra algo.
EXTRACTOR = (
    "Vas a leer un pedazo de conversacion entre una persona y un robot.\n"
    "Las lineas que empiezan con 'user:' las dice LA PERSONA y hablan de su "
    "vida. Las que empiezan con 'assistant:' las dice el robot y no aportan "
    "datos sobre nadie.\n\n"
    "Sacas los datos que sigan sirviendo dentro de un mes: nombres propios, "
    "parentescos, donde trabaja o vive alguien, gustos estables, decisiones.\n\n"
    "NO son datos y no los escribas:\n"
    "- como se siente o que necesita alguien en este momento\n"
    "- lo que hace o dice el robot, ni como es el robot\n"
    "- resumenes de lo que se hablo\n"
    "- frases sobre 'el usuario' sin un nombre propio adentro\n\n"
    "Cuidado con de quien es cada cosa. Si la persona dice 'mi hermana Ana vive "
    "en Cali' y despues 'yo trabajo en X', lo de Cali es de Ana y lo del trabajo "
    "es de ella, no de Ana. Si no sabes de quien es un dato, no lo escribas.\n\n"
    "Una linea por dato, sin vinetas ni numeros, en tercera persona y con el "
    "nombre de quien se trate.\n"
    "Casi siempre no hay ninguno. Cuando no lo haya, respondes exactamente: NADA"
)


def _marca(db) -> int:
    m = db.get(Marcador, CLAVE_MARCA)
    try:
        return int(m.valor) if m and m.valor else 0
    except (TypeError, ValueError):
        return 0


def _poner_marca(db, hasta: int) -> None:
    m = db.get(Marcador, CLAVE_MARCA)
    if m:
        m.valor = str(hasta)
    else:
        db.add(Marcador(clave=CLAVE_MARCA, valor=str(hasta)))
    db.commit()


def turnos_sin_leer() -> int:
    db = SessionLocal()
    try:
        return (db.query(func.count(Conversation.id))
                .filter(Conversation.id > _marca(db)).scalar() or 0)
    finally:
        db.close()


def consolidar(generar) -> dict:
    """Relee los turnos nuevos y guarda lo que quede en pie.

    `generar(mensajes) -> str` se inyecta en vez de importar llm_service: asi
    esto se puede probar sin cargar 2 GB de modelo, y deja claro que la
    consolidacion no decide CUANDO corre — eso lo decide quien la llama, que es
    el unico que sabe si la CPU esta libre.

    La marca avanza SIEMPRE, aunque el lote no produzca nada. Si no, un rato de
    charla sin hechos haria releer los mismos turnos para siempre.
    """
    with _lock:
        if _estado["consolidando"]:
            return {"ok": False, "motivo": "ya esta corriendo"}
        _estado["consolidando"] = True
    try:
        db = SessionLocal()
        try:
            desde = _marca(db)
            turnos = (db.query(Conversation)
                      .filter(Conversation.id > desde)
                      .order_by(Conversation.id).limit(LOTE).all())
            if not turnos:
                return {"ok": True, "leidos": 0, "guardadas": 0}
            hasta = turnos[-1].id
            charla = "\n".join(f"{t.role}: {t.content}" for t in turnos)
        finally:
            db.close()

        salida = generar([{"role": "system", "content": EXTRACTOR},
                          {"role": "user", "content": charla}])

        guardadas = []
        if salida and salida.strip().upper() != "NADA":
            for linea in salida.split("\n"):
                linea = linea.strip(" -*	")
                if len(linea) < 8:          # ruido del modelo, no un hecho
                    continue
                r = guardar(linea, tipo="hecho", fuente="consolidado",
                            conversation_id=hasta, vigente=False)
                if r.get("guardada"):
                    guardadas.append(r["texto"])

        db = SessionLocal()
        try:
            _poner_marca(db, hasta)
        finally:
            db.close()

        _estado["consolidadas"] += len(guardadas)
        _estado["ultima_consolidacion"] = time.strftime("%H:%M:%S")
        _estado["error"] = None
        return {"ok": True, "leidos": len(turnos), "guardadas": len(guardadas),
                "textos": guardadas, "hasta": hasta}
    except Exception as e:
        _estado["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return {"ok": False, "motivo": _estado["error"]}
    finally:
        with _lock:
            _estado["consolidando"] = False


def estado() -> dict:
    db = SessionLocal()
    try:
        total = db.query(func.count(Memoria.id)).scalar() or 0
        por_fuente = dict(db.query(Memoria.fuente, func.count(Memoria.id))
                          .group_by(Memoria.fuente).all())
        por_tipo = dict(db.query(Memoria.tipo, func.count(Memoria.id))
                        .group_by(Memoria.tipo).all())
        esperando = (db.query(func.count(Memoria.id))
                     .filter(Memoria.vigente.is_(False)).scalar() or 0)
        pendientes = (db.query(func.count(Conversation.id))
                      .filter(Conversation.id > _marca(db)).scalar() or 0)
    except Exception as e:
        return dict(_estado, error=f"{type(e).__name__}: {str(e)[:120]}")
    finally:
        db.close()
    return dict(_estado, total=total, por_fuente=por_fuente, por_tipo=por_tipo,
                esperando=esperando,
                turnos_sin_leer=pendientes, umbral=UMBRAL,
                embed=emb.estado())
