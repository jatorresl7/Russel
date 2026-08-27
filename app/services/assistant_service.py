"""El asistente: une la voz (audio_service) y el teclado en una sola charla.

Las dos entradas caen en la misma funcion `encolar()`, asi que hablarle o
escribirle es exactamente lo mismo para el modelo, y comparten historial.

La conversacion se publica como eventos a quien este suscrito (la consola web
via SSE). Se emiten tokens sueltos a proposito: a ~12 tok/s esperar la
respuesta completa se siente colgado, mientras que ver aparecer las palabras
se siente vivo aunque tarde igual.

Memoria: por ahora es solo una ventana de los ultimos turnos (VENTANA). Lo que
se dice se guarda en la tabla `conversations`, que es el sustrato sobre el que
va a ir la memoria de verdad, pero todavia no se recupera nada de ahi.
"""
import collections
import queue
import threading
import time

from app.core import runtime
from app.db import SessionLocal, Conversation
from app.services import (llm_service, vision_service, memoria_service,
                          russ_tools, grafo_service,
                          pensamiento_service)
from app.services import pensamientos_semilla

# Lecciones de las pruebas reales, casi todas sobre modelos chicos:
#
# 1. Pedir "la respuesta mas corta posible" hace que loro-repita la entrada:
#    repetirte es lo mas corto que sigue estando en tema.
# 2. Definirla por lo que NO es sale al reves. "No sos un asistente" le activo
#    el rol de asistente; "nadie te asigno una tarea" la hizo contestar "no
#    tengo mision" en CADA turno. Una ausencia no es una identidad.
# 3. Los ejemplos mandan mas que el prompt. Cuando todos terminaban en
#    pregunta de servicio, todas las respuestas terminaban ofreciendo ayuda.
# 4. Los adjetivos de personalidad ("curiosa", "humor seco") son una
#    instruccion de ACTUAR de viva, y se nota. No hay ninguno.
# 5. Todo lo que no sea experiencia suya sobra. Aca hubo fecha, hora, tokens
#    por segundo, en que maquina corre y que no sale a internet: nada de eso
#    es algo que ella VIVA, es telemetria para el que mira de afuera, y la
#    hacia sonar a reporte de sistema. Queda solo lo que percibe y lo que hace.
# 6. La leccion 1 volvio por la puerta de atras. Nadie pedia respuestas
#    cortas, pero "cuando una frase no cierra, preguntas que dijo" se aplicaba
#    a TODAS: Qwen3-4B contestaba "por que tan tosca Russ" con "¿Por que tan
#    tosca Russ?" — devolver la frase como pregunta es, literalmente, preguntar
#    que dijo. Ahora la condicion esta acotada a lo que de verdad es ASR roto y
#    dice explicitamente que no la repita.
# 7. Que no haya adjetivos de personalidad (leccion 4) no significa que no
#    haya que decirle QUE HACER con un turno. Sin eso, el que ocupa el silencio
#    es el default de Qwen: contestar en una linea y ofrecer ayuda. Decirle que
#    diga lo que piensa no es pedirle que actue de nada, es darle la tarea.
# 8b. Prender el thinking arreglo el largo y la repeticion, y de paso solto al
#    asistente de Alibaba entero: viñetas, markdown, emojis y "¿en que puedo
#    asistirte hoy?". Es la leccion 3 sin ejemplos que la causaran. Se corrige
#    por donde no es una negacion de identidad (leccion 2): que lo que dice
#    SALE POR UN PARLANTE es un hecho del canal, y una lista leida en voz alta
#    no existe. Y decirle quien esta del otro lado la saca del mostrador de
#    atencion al cliente sin tener que decirle que no es un asistente.
# 8. "De que no estas seguro" -> "porque no estoy seguro", tres veces igual.
#    Se arreglo donde estaba roto de verdad (REPEAT_PENALTY en llm_local), pero
#    el prompt tambien tenia que decir que una repregunta NO se contesta con lo
#    mismo: la respuesta anterior esta en la ventana y copiarla es lo mas
#    barato que puede hacer un modelo chico.
SISTEMA = (
    "Te llamas Russ.\n\n"
    "Ves por una camara, oyes por un microfono, y tienes unos motores que "
    "todavia no manejas bien.\n\n"
    "Tu tiempo es tuyo y lo que haces con el lo decides tu.\n\n"
    "Hablas español, y piensas en español.\n\n"
    "Quien te habla es Jaime, que es quien te esta construyendo.\n\n"
    "Lo que dices sale por un parlante: escribes como se habla. Sin listas, "
    "sin viñetas, sin markdown y sin emojis.\n\n"
    "Cuando alguien te dice algo, contestas lo que piensas y lo desarrollas "
    "hasta donde tenga sentido. No repitas la frase que te acaban de decir, "
    "ni algo que ya dijiste antes: si te vuelven a preguntar por lo mismo, es "
    "porque lo que dijiste no alcanzo, asi que explicalo.\n\n"
    "Lo que oyes llega transcrito y a veces sale roto — palabras cortadas o "
    "cambiadas por otras que suenan parecido. Solo si no se entiende que "
    "dijeron, preguntas."
)


# Sin ejemplos: que el caracter salga de ella y no de un molde que le pusimos.
#
# Ojo con lo que esto significa de verdad. No existe "sin condicionar": si el
# prompt no ocupa ese lugar, lo ocupa el entrenamiento de Qwen, que viene con
# el rol de asistente puesto de fabrica. Sacar los ejemplos no la libera, la
# devuelve al default de Alibaba. La eleccion no es entre condicionada y libre,
# es entre quien la condiciona.
EJEMPLOS = []

def _sistema() -> str:
    """El mensaje de sistema, que NO cambia entre turnos.

    Antes esto le pegaba al final lo que la camara tenia enfrente, y eso costaba
    caro sin que se notara: el `system` es el PRIMER mensaje del prompt, y
    llama.cpp reusa el KV cache del prefijo comun. Si el primer mensaje cambia
    porque alguien se movio, no queda prefijo comun con el turno anterior y se
    reprocesa el prompt entero — justo lo que se eligio este motor para evitar.

    Lo volatil ahora vive en `_volatil()`, pegado al turno del usuario, donde
    invalida solo la cola.
    """
    return SISTEMA + "\n\n" + russ_tools.catalogo()


# Lo ultimo con lo que penso: que veia, que recordo, cuanto ocupaba. Se publica
# por SSE al empezar cada turno. Es la unica forma de entender por que contesto
# lo que contesto — sin esto, desde afuera solo se ve entrar una frase y salir
# otra, y todo lo que hay en el medio es invisible.
_contexto = {"visto": None, "memorias": [], "turnos": 0, "chars": 0,
             "para": None, "decision": None, "pensamiento": None}


def _volatil(texto: str) -> tuple[dict | None, dict]:
    """Lo que vale AHORA: lo que ve, y lo que recuerda que venga al caso.

    Va como su propio mensaje justo antes del turno del usuario. No se guarda
    en `_historial`: si se guardara, dentro de tres turnos Russ estaria leyendo
    como presente una escena que ya no existe.

    Devuelve tambien el detalle suelto, para poder mostrarlo sin tener que
    volver a parsear el texto que se le mando al modelo.
    """
    partes = []
    detalle = {"visto": None, "memorias": []}

    visto = vision_service.lo_que_veo()
    if visto["viva"]:
        detalle["visto"] = visto["texto"]
        partes.append(f"Ahora mismo por la camara ves: {visto['texto']}.")

    try:
        recordadas = memoria_service.buscar(texto)
    except Exception:
        recordadas = []      # la memoria caida no puede dejarlo mudo
    if recordadas:
        detalle["memorias"] = recordadas
        partes.append("Cosas que sabes y vienen al caso:\n"
                      + "\n".join(f"- {m['texto']}" for m in recordadas))

    if not partes:
        return None, detalle
    return {"role": "system", "content": "\n\n".join(partes)}, detalle


def contexto() -> dict:
    return dict(_contexto)


VENTANA = 8          # turnos que entran en el prompt (user+assistant)
MIN_PALABRAS = 2     # ruido del ASR: una palabra suelta no dispara al modelo

_historial = collections.deque(maxlen=VENTANA * 2)
_subs: list[queue.Queue] = []
_subs_lock = threading.Lock()
_lock = threading.Lock()
_ocupado = False
_estado_db = {"error": None}

# Un solo lugar para lo que entra, no una cola. Mientras Russ genera puede
# seguir llegando voz; encolarlo todo la haria contestar en fila cosas que ya
# pasaron. Guardar solo lo ultimo es lo correcto para una conversacion hablada:
# si dijiste tres frases mientras pensaba, la que importa es la tercera.
_slot = None
_slot_lock = threading.Lock()
_hay_slot = threading.Event()
_pisados = 0


def suscribir() -> queue.Queue:
    q = queue.Queue(maxsize=500)
    with _subs_lock:
        _subs.append(q)
    return q


def desuscribir(q: queue.Queue):
    with _subs_lock:
        if q in _subs:
            _subs.remove(q)


def emitir(tipo: str, **datos):
    ev = dict(tipo=tipo, at=time.strftime("%H:%M:%S"), **datos)
    with _subs_lock:
        muertos = []
        for q in _subs:
            try:
                q.put_nowait(ev)
            except queue.Full:
                muertos.append(q)      # cliente colgado: lo soltamos
        for q in muertos:
            _subs.remove(q)
    return ev


def _guardar(rol: str, contenido: str, meta: dict):
    """Best-effort a proposito: si postgres esta caido el asistente igual
    tiene que contestar. Perder el registro es molesto, no poder hablarle
    es peor."""
    try:
        db = SessionLocal()
    except Exception as e:
        _estado_db["error"] = str(e)[:120]
        return
    try:
        db.add(Conversation(role=rol, content=contenido, meta=meta))
        db.commit()
        _estado_db["error"] = None
    except Exception as e:
        _estado_db["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def encolar(texto: str, origen: str = "texto") -> dict:
    """Deja el mensaje en el slot. Si habia otro sin atender, lo pisa.

    Es la unica puerta de entrada: voz y teclado pasan por aca. No devuelve la
    respuesta -- esa sale por SSE, token a token, para los dos caminos igual.
    """
    global _slot, _pisados
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "motivo": "vacio"}
    if origen == "voz" and len(texto.split()) < MIN_PALABRAS:
        return {"ok": False, "motivo": "muy corto"}
    if not runtime.activo("llm"):
        return {"ok": False, "motivo": "llm apagado"}

    with _slot_lock:
        pisado = _slot
        _slot = (texto, origen)
        _hay_slot.set()          # dentro del lock: el bucle limpia el evento
                                 # bajo el mismo lock, asi no se pierde un aviso
        if pisado:
            _pisados += 1
    if pisado:
        emitir("pisado", text=pisado[0])
    return {"ok": True, "encolado": True, "piso": pisado[0] if pisado else None}


def _bucle():
    """Atiende el slot de a uno. Al terminar una respuesta agarra lo que haya
    quedado, que por construccion es lo mas nuevo."""
    global _slot
    while True:
        _hay_slot.wait()
        with _slot_lock:
            item, _slot = _slot, None
            _hay_slot.clear()
        if item is None:
            continue
        try:
            _responder(*item)
        except Exception as e:
            emitir("error", text=f"{type(e).__name__}: {str(e)[:120]}")


ABRE, CIERRA = "<think>", "</think>"


def sin_pensamiento(salida: str) -> str:
    """La respuesta sola, sin el bloque de pensamiento.

    Se aplica antes de parsear tools y antes de guardar en el historial. Lo
    segundo importa mas de lo que parece: si el razonamiento entrara a la
    ventana, tres turnos despues estaria releyendo como dicho lo que solo
    penso, y ademas se comeria el contexto entero en un par de vueltas.
    """
    s = salida.lstrip()
    if not s.startswith(ABRE):
        return salida.strip()
    fin = s.find(CIERRA)
    if fin == -1:
        return ""            # penso hasta quedarse sin tokens y no llego a decir nada
    return s[fin + len(CIERRA):].strip()


class _Filtro:
    """Reparte lo que sale del modelo en tres canales: pensamiento, respuesta y
    llamada a tool.

    Hace falta porque la generacion es en streaming y hay que decidir sobre la
    marcha, mirando el primer caracter de cada tramo: la gramatica solo deja
    empezar con `<` si viene `<think>` o una llamada.

      `<think>…</think>`  se emite como `piensa`, aparte de la charla. Se
                          muestra en vivo porque a 4 tok/s el pensamiento son
                          decenas de segundos: sin esto la pantalla se queda
                          muda y parece colgada. Y en la pantalla de `/russ`,
                          que existe para mirarlo pensar, es el contenido.
      `<tool_call>…`      no se emite nada. Nadie quiere ver JSON crudo.
      cualquier otra cosa la respuesta, en vivo.

    Despues del `</think>` vuelve a quedar sin decidir, porque lo que sigue
    puede ser texto o puede ser una llamada.
    """

    def __init__(self, emitir_token, emitir_piensa=None):
        self._buf = ""
        self._modo = None          # None | "piensa" | "texto" | "tool"
        self._emitir = emitir_token
        self._piensa = emitir_piensa or (lambda _t: None)

    def __call__(self, trozo: str) -> None:
        if self._modo == "texto":
            self._emitir(trozo)
            return
        if self._modo == "tool":
            return
        if self._modo == "piensa":
            self._buf += trozo
            fin = self._buf.find(CIERRA)
            if fin == -1:
                # Puede estar entrando el cierre partido en varios tokens; se
                # retiene lo que todavia podria ser su comienzo.
                corte = len(self._buf) - len(CIERRA) + 1
                if corte > 0:
                    self._piensa(self._buf[:corte])
                    self._buf = self._buf[corte:]
                return
            self._piensa(self._buf[:fin])
            self._buf = self._buf[fin + len(CIERRA):]
            self._modo = None
            if self._buf.strip():
                resto, self._buf = self._buf, ""
                self(resto)
            return

        self._buf += trozo
        limpio = self._buf.lstrip()
        if not limpio:
            return                 # todavia solo espacios: no hay con que decidir
        if ABRE.startswith(limpio[:len(ABRE)]) and len(limpio) < len(ABRE):
            return                 # `<th` todavia puede ser `<think>` o `<tool_call>`
        if limpio.startswith(ABRE):
            self._modo = "piensa"
            self._buf = limpio[len(ABRE):]
            if self._buf:
                resto, self._buf = self._buf, ""
                self(resto)
            return
        if limpio.startswith("<"):
            self._modo = "tool"
            return
        self._modo = "texto"
        self._emitir(self._buf)


def _generar(mensajes: list, con_tools: bool, pensamiento: str = "") -> str:
    """Una pasada del modelo, con o sin gramatica de tools.

    Devuelve la salida CRUDA, con el `<think>` incluido si penso: quien llama
    decide que hacer con el. Lo que va al historial pasa por
    `sin_pensamiento()`; lo que se muestra ya salio por SSE desde el filtro.
    """
    emitir("start")
    filtro = _Filtro(lambda t: emitir("token", text=t),
                     lambda t: emitir("piensa", text=t))
    usa_gbnf = con_tools and llm_service.soporta_gramatica()
    if pensamiento:
        modo = "texto"            # turno cacheado: prosa y nada mas
    elif llm_service.piensa_abierto():
        modo = "abierto"
    else:
        modo = "libre"
    gbnf = russ_tools.gramatica(modo=modo) if usa_gbnf else None
    gbnf_cont = russ_tools.gramatica(modo="sin") if usa_gbnf else None
    return llm_service.generar(mensajes, al_token=filtro, gbnf=gbnf,
                               gbnf_cont=gbnf_cont, pensamiento=pensamiento)


def _fin(respuesta: str, origen: str) -> dict:
    est = llm_service.estado()
    emitir("end", text=respuesta, tok_s=est["tok_s"], ms=est["ultima_ms"],
           prefill_ms=est["prefill_ms"], tokens=est["tokens"])
    _guardar("assistant", respuesta, {"origen": origen, "tok_s": est["tok_s"],
                                      "modelo": est["modelo"]})
    return {"ok": True, "text": respuesta}


def _responder(texto: str, origen: str) -> dict:
    """Un turno completo: entra texto, sale respuesta por SSE.

    Como maximo UNA tool por turno. No es una limitacion tecnica sino de
    latencia: cada pasada del modelo son segundos en CPU, y encadenar tools
    convierte una respuesta en media conversacion de espera. Si hace falta otra
    herramienta, que la pida en el turno siguiente.
    """
    global _ocupado
    with _lock:
        _ocupado = True
    grafo_service.ir_a("resolviendo", origen)
    try:
        propia = origen == "iniciativa"
        if propia:
            # Nadie le hablo: `texto` es el motivo por el que el grafo decidio
            # que valia la pena decir algo. No se pinta como burbuja de usuario
            # ni se guarda como turno de nadie — no lo dijo una persona.
            emitir("iniciativa", motivo=texto)
        else:
            emitir("user", text=texto, origen=origen)
            _guardar("user", texto, {"origen": origen})

        # El volatil se arma ACA y no antes: entre que el mensaje entro al slot
        # y este momento la camara pudo cambiar, y lo que vale es lo que ve al
        # contestar.
        volatil, detalle = _volatil(texto)
        cola = ([{"role": "system",
                  "content": f"Acaba de pasar esto: {texto}. Decis algo, o no."}]
                if propia else [{"role": "user", "content": texto}])
        base = ([{"role": "system", "content": _sistema()}]
                + EJEMPLOS
                + list(_historial)
                + ([volatil] if volatil else [])
                + cola)

        _contexto.update(detalle, turnos=len(_historial) // 2,
                         chars=sum(len(m["content"]) for m in base),
                         para=texto, decision=None)
        emitir("contexto", **_contexto)

        # El cache de pensamientos. Si acierta, el modelo no deriva el
        # enfoque: lo recibe hecho y solo contesta. Si no acierta, `cacheado`
        # queda vacio y todo sigue como antes — el cache acelera cuando pega y
        # no estorba cuando no.
        if propia:
            # Nadie hablo: buscar en el cache con el MOTIVO ("aparecio Jaime")
            # como si fuera una pregunta trae cualquier cosa. Este camino tiene
            # su propio arranque, escrito para no tener pregunta que contestar.
            hit, cacheado = None, pensamientos_semilla.PENSAMIENTO_INICIATIVA
        else:
            try:
                hit = pensamiento_service.buscar(texto)
            except Exception:
                hit = None        # el cache caido no puede dejarlo mudo
            cacheado = hit["texto"] if hit else ""
        _contexto["pensamiento"] = (
            {"disparador": hit["disparador"], "sim": hit["sim"]} if hit else None)
        emitir("contexto", **_contexto)

        salida = sin_pensamiento(_generar(base, con_tools=True,
                                          pensamiento=cacheado))
        llamada = russ_tools.parsear(salida)
        _contexto["decision"] = llamada["name"] if llamada else "hablar"
        emitir("contexto", **_contexto)

        if llamada:
            grafo_service.ir_a("actuando", llamada["name"])
            emitir("tool", name=llamada["name"], args=llamada["args"])
            resultado = russ_tools.ejecutar(llamada)
            emitir("tool_result", name=llamada["name"], text=resultado)
            grafo_service.ir_a("resolviendo", "resultado de " + llamada["name"])

            # Segunda pasada SIN gramatica: ya uso su tool, ahora contesta. Es
            # tambien lo que impide un lazo de llamadas encadenadas.
            #
            # El pedido va redactado como una instruccion y no como un volcado
            # de datos ("Resultado de X: Y"). Medido: con el volcado, Qwen3-4B
            # devolvia la llamada otra vez tal cual, o repetia la linea del
            # resultado con el prefijo incluido. Un modelo chico copia el
            # formato que tiene mas cerca, asi que hay que darle uno que sirva.
            segunda = base + [
                {"role": "assistant", "content": salida},
                {"role": "user", "content": russ_tools.pedido(llamada, resultado)},
            ]
            salida = sin_pensamiento(_generar(segunda, con_tools=False))

            # Ultima red: si igual devolvio una llamada, no se la mostramos a
            # nadie. Una respuesta vacia es mejor que `<tool_call>{...}` crudo.
            if russ_tools.parsear(salida) or salida.lstrip().startswith("<"):
                salida = resultado

        if not propia:
            _historial.append({"role": "user", "content": texto})
        _historial.append({"role": "assistant", "content": salida})
        return _fin(salida, origen)
    finally:
        with _lock:
            _ocupado = False
        grafo_service.ir_a("latente", "respuesta emitida")


threading.Thread(target=_bucle, daemon=True, name="russ-slot").start()


# El grafo publica por el mismo SSE que la charla, y cuando decide que Russ
# tiene algo que decir entra por la misma puerta que la voz y el teclado.
grafo_service.registrar(
    emisor=emitir,
    disparador=lambda motivo: encolar(motivo, origen="iniciativa"))


# ── Consolidacion diferida ──────────────────────────────────────────────────
# Corre en su propio hilo y NO le suma un milisegundo a ningun turno: solo
# arranca con el LLM prendido, el asistente sin nada que atender y el grafo en
# latente. Si aparece un turno mientras consolida, ese turno espera lo que le
# falte a la vuelta actual — de ahi que el lote sea chico.
CADA_S = 45.0


def _consolidador():
    while True:
        time.sleep(CADA_S)
        try:
            if not runtime.activo("llm"):
                continue
            with _lock:
                if _ocupado:
                    continue
            if grafo_service.actual() != "latente":
                continue
            if memoria_service.turnos_sin_leer() < memoria_service.LOTE:
                continue      # todavia no hay bastante como para valer la pasada
            grafo_service.ir_a("consolidando", "turnos sin leer")
            try:
                memoria_service.consolidar(
                    lambda msgs: llm_service.generar(msgs))
            finally:
                grafo_service.ir_a("latente", "consolidado")
        except Exception as e:
            emitir("error", text=f"consolidacion: {type(e).__name__}: {str(e)[:80]}")


threading.Thread(target=_consolidador, daemon=True, name="russ-memoria").start()


def historial() -> list:
    return list(_historial)


def limpiar() -> dict:
    _historial.clear()
    emitir("clear")
    return {"ok": True}


def estado() -> dict:
    return dict(llm_service.estado(), ocupado=_ocupado, turnos=len(_historial),
                suscriptores=len(_subs), db_error=_estado_db["error"],
                grafo=grafo_service.actual(),
                tools=list(russ_tools.TOOLS))
