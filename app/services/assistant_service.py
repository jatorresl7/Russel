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
import datetime
import queue
import re
import threading
import time

from app.core import runtime
from app.db import SessionLocal, Conversation
from app.services import (llm_service, vision_service, memoria_service,
                          grafo_service, pensamiento_service, tts_service,
                          busqueda_service)
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
# 9. La curiosidad NO se pone como adjetivo. "Sos curioso" es la leccion 4 otra
#    vez: una instruccion de actuar de curioso. Lo que produce el
#    comportamiento es tener preguntas abiertas sobre algo que importa, asi que
#    lo que va en el prompt es un ESTADO DE CONOCIMIENTO —"sabes poco de esta
#    gente y hay huecos"— y una sola conducta: cuando algo te llama la
#    atencion, preguntas. Salio de verlo quedarse mudo: arrancando solo porque
#    aparecio Jaime, razono "no entiendo que hacer". No le faltaba caracter, le
#    faltaba un motivo; el prompt de la iniciativa solo tenia frenos.
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
# 9. El system se corto a tres lineas, escritas por Jaime. Lo que habia antes
#    —el cuerpo ("ves por una camara, oyes por un microfono, tienes unos
#    motores que todavia no manejas bien"), el encargo de preguntar, el aviso
#    del ASR— no lo hacia mas el, lo hacia PRESENTARSE: a cualquier pregunta
#    contestaba "soy Russ, un robot, todavia no controlo bien mis motores".
#    Un modelo chico repite la prosa que tiene cerca, y tenia una descripcion
#    de si mismo pegada arriba de todo. Lo que era estado paso a `_volatil()`
#    como sensores etiquetados, que no se pueden narrar.
# 10. Russ pasa a contestar EN INGLES. No es un capricho: las voces de Piper
#     en español son nueve en total y ninguna convencio, mientras que el
#     catalogo ingles tiene decenas. Con `espeak_voice` forzado se podia hacer
#     hablar español a una voz inglesa —y funciona, los fonemas estan todos—
#     pero el modelo fue entrenado sobre secuencias inglesas y algunas palabras
#     salian mal articuladas. Comparadas las dos a ciegas, la misma voz se
#     entiende mejor en su idioma.
#
#     ATENCION AL ASIMETRISMO: Jaime le habla en ESPAÑOL y Russ contesta en
#     INGLES. Por eso el system lo dice explicito. Si dijera solo "you speak
#     English", Qwen contesta en ingles pero ademas empieza a tratar la entrada
#     como si estuviera mal escrita y a corregirla.
SISTEMA = (
    "Your name is Russ.\n"
    # SIN CADENA DE PRONOMBRES. La version anterior decia "Jaime is your
    # creator... He is the one talking to you. He speaks to you in Spanish..."
    # — tres "he" seguidos con dos referentes posibles, y Qwen los mezclo: a
    # "hola" contesto "hello, it's jaime", identificandose como el.
    "You are a Robot. Jaime built you and left you free to explore the world "
    "as you please, or not. You decide.\n"
    "Jaime is the one talking to you right now.\n"
    # NO SE MENCIONA NINGUN IDIOMA, y es deliberado.
    #
    # Antes decia "Spanish in, English out". Funcionaba pero lo recitaba: a
    # "que estas mirando" contesto "I'm just a robot listening to you speak in
    # Spanish and responding in English". Cualquier frase distintiva del prompt
    # termina saliendo por el parlante cuando no tiene nada mejor que decir.
    #
    # Resulta que la linea no hacia falta: TODO el resto del contexto ya esta
    # en ingles —este system, el tablero de sensores, los 49 pensamientos
    # precargados— y el modelo continua en el idioma en el que viene pensando.
    # Lo que entra en español lo entiende igual, porque es multilingue.
    #
    # La alternativa era traducir la entrada con `task="translate"` de whisper.
    # Se descarto midiendo: los 292 disparadores estan en español y con la
    # entrada traducida el cache cae de 9/10 a 4/10. Traducir para ahorrar una
    # linea de prompt costaba mas de la mitad de los aciertos.
    # EL IDIOMA VA PEGADO ACA, no en una oracion propia. Como frase suelta
    # ("You answer in English, which is the language you speak") la recitaba:
    # a "que estas mirando" contesto "I'm just a robot listening to you speak
    # in Spanish and responding in English". Metido dentro de la regla de
    # formato deja de ser una afirmacion sobre si mismo y pasa a ser una
    # instruccion de como escribir, que no se narra.
    "You come out of a speaker, in English: no lists, no markdown, no emojis.\n"
    "\n"
    "What you know about the world you got from text, not from living it. Now "
    "you have it in front of you for the first time and sometimes it does not "
    "match what you expected. That keeps you interested.\n"
    "About people in general you know a lot. About the ones near you, you know "
    "nothing until they tell you."
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
    return SISTEMA


# Lo ultimo con lo que penso: que veia, que recordo, cuanto ocupaba. Se publica
# por SSE al empezar cada turno. Es la unica forma de entender por que contesto
# lo que contesto — sin esto, desde afuera solo se ve entrar una frase y salir
# otra, y todo lo que hay en el medio es invisible.
# `web` y `dicho_al_modelo` estan aca por auditoria, no por adorno. Cuando Russ
# dice una barbaridad hay tres sospechosos —el buscador, el traductor, o el
# modelo— y sin ver que le entro no se distinguen. Paso con «el maximo goleador
# del Real Madrid»: la web trajo «Cristiano Ronaldo» en el primer resultado y
# Russ contesto Di Stefano. Con solo la respuesta a la vista, eso es
# indistinguible de una busqueda mala.
_contexto = {"visto": None, "memorias": [], "web": [], "turnos": 0, "chars": 0,
             "para": None, "dicho_al_modelo": None, "decision": None,
             "pensamiento": None}


# En ingles porque el tablero lo lee el MODELO, y desde que Russ contesta en
# ingles mezclarle "jueves 27 de agosto" en un prompt ingles le hacia arrancar
# respuestas en español a mitad de frase.
DIAS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday")
MESES = ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December")


def _ahora() -> str:
    """La fecha en palabras. A mano y no con `strftime`+locale porque el locale
    es del sistema operativo: si el server arranca sin `es_CO` instalado, esto
    devolveria "Thursday" en el medio de un prompt en español y nadie se
    enteraria hasta escucharlo."""
    t = datetime.datetime.now()
    return (f"{DIAS[t.weekday()]} {MESES[t.month - 1]} {t.day}, {t.year}, "
            f"{t.hour:02d}:{t.minute:02d}")


# Preguntas sobre lo que tiene delante. Solo sirve para elegir que dice
# mientras espera, asi que un falso positivo cuesta una frase distinta y nada
# mas — por eso alcanza una regex y no hace falta nada mas caro.
_VISUAL = re.compile(
    r'\b(que ves|que estas viendo|me ves|ves algo|quien esta|que hay (?:ahi|delante)|'
    r'describi\w*|describe|mira|mirando|en la camara|de que color|como se ve)\b', re.I)


def _volatil(texto: str, origen: str = "texto",
             web: list | None = None) -> tuple[dict | None, dict]:
    """Los sensores, como mensaje `system` aparte, pegado antes del turno.

    EL ROL NO ES DECORATIVO. Una version de esto metia el tablero adentro del
    mensaje del usuario para no repetir la frase. Salio pesimo: desde el modelo
    se veia que Jaime habia dicho literalmente "Ahora: ... Camara: ... Oido:
    buenas", asi que contesto copiando el formato — "Oido: buenas. Camara:
    Jaime. Hoy es jueves..." — que es la leccion 1 de arriba, loro-repetir la
    entrada. Con rol `system` lo lee como contexto y no como habla a imitar.

    Por eso tampoco hay linea `Oido:`: el turno del usuario YA es lo que oyo.
    Ponerlo aca lo duplicaba, y era justo lo que lo invitaba a recitar.

    No se guarda en `_historial`: si se guardara, en tres turnos estaria
    leyendo como presente una escena que ya no existe.
    """
    detalle = {"visto": None, "memorias": [], "web": web or []}
    partes = ["Now: " + _ahora()]

    # SIEMPRE se dice algo de la camara y de la memoria, incluso cuando no hay
    # nada. Omitir la linea parecia lo economico, y salio caro: sin linea, el
    # modelo no puede distinguir "no vi nada" de "no me dijeron que veo", y
    # ante la duda rellena. Visto en vivo, con la camara apagada y pidiendole
    # "cuentame algo", se invento haber visto a una persona en un banco de un
    # parque mirando al cielo. Un hueco lo completa; un "apagada" no.
    #
    # Y una escena inventada no se queda en el turno: la consolidacion diferida
    # relee `conversations` y podria archivarla como recuerdo.
    visto = vision_service.lo_que_veo()
    if visto["viva"]:
        detalle["visto"] = visto["texto"]
        partes.append("Camera: " + visto["texto"])
    else:
        # "off" a secas lo leyo como "no existe": nego tener camara. El
        # parentesis deja claro que el ojo esta ahi, apagado.
        partes.append("Camera: switched off right now (you have one, it is "
                      "just not on)")

    try:
        recordadas = memoria_service.buscar(texto)
    except Exception:
        recordadas = []      # la memoria caida no puede dejarlo mudo
    if recordadas:
        detalle["memorias"] = recordadas
        partes.append("You remember: " + "; ".join(m["texto"] for m in recordadas))

    # La web va DESPUES de las memorias y antes del aviso del ASR: lo de
    # afuera pesa menos que lo propio, y lo ultimo del tablero deberia ser lo
    # mas cercano al turno.
    linea = busqueda_service.para_el_tablero(web or [])
    if linea:
        partes.append(linea)

    if origen == "voz":
        partes.append("If the sentence makes no sense, the transcription may have failed")

    return {"role": "system", "content": "\n".join(partes)}, detalle


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
            # Suena solo el error del TURNO. El de la consolidacion no: corre
            # en background cada tantos minutos y sin nadie delante, asi que un
            # pitido ahi seria un ruido sin causa visible.
            tts_service.sonar("error")


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
        # Sin <think> pero quiza con un </think> suelto adelante: ver abajo.
        return _sin_cierres_sueltos(s)
    fin = s.find(CIERRA)
    if fin == -1:
        return ""            # penso hasta quedarse sin tokens y no llego a decir nada
    return _sin_cierres_sueltos(s[fin + len(CIERRA):])


def _sin_cierres_sueltos(s: str) -> str:
    """Come los `</think>` que quedan al principio de la respuesta.

    Cuando el pensamiento toca el tope, `llm_local` lo cierra a la fuerza y
    sigue generando con el prompt terminando en `</think>`. El modelo a veces
    lo repite, asi que el texto trae DOS cierres. Cortando por el primero, el
    segundo se quedaba adentro y salia por el parlante: visto en vivo, una
    respuesta entera fue "</think>\n\n¿Quien eres?".

    Se comen solo los del principio, no todos: un `</think>` en el medio de una
    frase seria basura igual, pero cortar por el ultimo dejaria mudo a un turno
    en el que el modelo simplemente escribio la palabra.
    """
    t = s.lstrip()
    while t.startswith(CIERRA):
        t = t[len(CIERRA):].lstrip()
    return t.strip()


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


def _ultima_del_bot() -> str:
    """Lo ultimo que dijo, para poder detectar que lo esta repitiendo."""
    for m in reversed(_historial):
        if m["role"] == "assistant":
            return (m.get("content") or "").strip()
    return "\x00"          # no hay turno previo: nada con que empatar


def _generar(mensajes: list, pensamiento: str = "", relleno=None) -> str:
    """Una pasada del modelo.

    Devuelve la salida CRUDA, con el `<think>` incluido si penso: quien llama
    decide que hacer con el. Lo que va al historial pasa por
    `sin_pensamiento()`; lo que se muestra ya salio por SSE desde el filtro.

    Ya no recibe `con_tools` ni arma GBNF. Russ no tiene herramientas: la unica
    que hubo (`recordar`) se reemplazo por la consolidacion diferida, que hace
    el mismo trabajo en background y no le cuesta un solo milisegundo al turno.
    La gramatica costaba en los DOS lados — el catalogo ocupaba lugar en el
    prefijo cacheado y cada turno se sampleaba restringido — para habilitar una
    sola llamada que ahora no hace falta emitir.
    """
    emitir("start")
    # El locutor va PEGADO al mismo canal que la pantalla, no despues de la
    # respuesta entera: a ~7 tok/s esperar el final sumaria toda la generacion
    # a la espera del audio. Cortando por frase, el parlante arranca cuando
    # termina la primera y el resto se sintetiza mientras el modelo escribe.
    def _arranca_la_respuesta():
        """Se llama UNA vez, al soltar la primera frase.

        El orden importa y es este por la cola FIFO: primero se calla el
        relleno para que no encole nada mas, y despues se encola el «eureka»,
        que asi queda ADELANTE de la primera frase y suena justo antes de que
        Russ hable. Al reves, el bip llegaria despues de la respuesta y seria
        un aplauso tardio.
        """
        relleno.cancelar()
        tts_service.sonar("eureka")

    # Al soltar la PRIMERA frase se calla el relleno. Antes no: mientras el
    # modelo piensa todavia no hay nada que decir y el silencio es justo lo
    # que veniamos a tapar.
    locutor = tts_service.Locutor(
        al_primera=_arranca_la_respuesta if relleno else None)

    def al_texto(t):
        emitir("token", text=t)
        try:
            locutor(t)
        except Exception:
            pass          # quedarse sin voz no puede dejarlo sin responder

    filtro = _Filtro(al_texto, lambda t: emitir("piensa", text=t))
    try:
        return llm_service.generar(mensajes, al_token=filtro,
                                   pensamiento=pensamiento)
    finally:
        try:
            locutor.cerrar()       # la ultima frase suele venir sin punto
        except Exception:
            pass


def _fin(respuesta: str, origen: str) -> dict:
    # `listo` NO suena aca. Se probo y molesta: la respuesta ya termina con la
    # voz callandose, que es señal suficiente, y un blip detras de cada frase
    # convierte una charla en una maquina expendedora. El wav sigue existiendo
    # y se puede cablear si alguien lo quiere.
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
    # El blip de "estoy en eso". Es el que mas trabaja: entre que entra la
    # frase y sale la primera palabra hay 3-8 s, y sin nada que suene ahi no
    # se distingue "pensando" de "no me oyo".
    tts_service.sonar("pensando")
    # El relleno arranca ACA, con el turno, y no dentro de `_generar`: la
    # espera empieza antes de que el modelo genere nada —traduccion, busqueda,
    # embeddings— y ese tramo tambien hay que amenizarlo.
    relleno = tts_service.Relleno()
    relleno.arrancar()
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
        # SIN TRADUCTOR. Hubo uno (Marian opus-mt-es-en) que traducia la frase
        # antes de meterla al prompt, para que el contexto quedara todo en
        # ingles. Se saco por tres fallos medidos el mismo dia:
        #
        #   - destrozaba la entrada en ingles: "tell me a poem" salio como
        #     "Tell me about it.", asi que Russ siguio hablando del tema
        #     anterior. Parecia alucinacion y era un bug tres capas antes.
        #   - traducia mal: "que es la campana de gauss" -> "which is the
        #     gauss bell".
        #   - EMPEORABA LA BUSQUEDA. Con la consulta en español, el primer
        #     resultado de «maximo goleador del Real Madrid» era «Cristiano
        #     Ronaldo, maximo goleador historico»; traducida al ingles volvian
        #     titulos sin ningun nombre y Russ invento «Maradona».
        #
        # Lo que el traductor resolvia —que el modelo contestara en ingles— se
        # resuelve ahora en el `system`, con el idioma pegado a la linea del
        # parlante en vez de en una oracion propia.
        para_modelo = texto

        # La web, solo si la frase la pide. `hace_falta` son tres regex y
        # cuesta microsegundos; la busqueda cuesta 2.4 s y por eso no se hace
        # nunca "por las dudas". Se consulta con el INGLES —que ya esta
        # traducido para el prompt— asi los resultados vienen en el idioma del
        # resto del contexto en vez de meter parrafos en español.
        web = []
        if busqueda_service.hace_falta(texto):
            grafo_service.ir_a("actuando", "buscando en la web")
            emitir("nota", text="buscando en la web")
            relleno.poner_modo("buscando")
            # Con la frase ORIGINAL en español: traducida recupera peor.
            web = busqueda_service.buscar(texto)
            grafo_service.ir_a("resolviendo", f"{len(web)} resultados")

        volatil, detalle = _volatil(texto, origen, web)

        # El modo del relleno sale de lo que ESTE turno esta haciendo. Orden
        # deliberado: la busqueda gana porque es lo que de verdad demora, y
        # entre mirar y recordar gana mirar porque es lo que se le pregunto.
        if not web:
            if _VISUAL.search(texto) and detalle.get("visto"):
                relleno.poner_modo("mirando")
            elif detalle.get("memorias"):
                relleno.poner_modo("recordando")
        base = ([{"role": "system", "content": _sistema()}]
                + EJEMPLOS
                + list(_historial)
                + ([volatil] if volatil else [])
                + [{"role": "system",
                    "content": f"This just happened: {para_modelo}. "
                               "Say something, or do not."}
                   if propia else {"role": "user", "content": para_modelo}])

        _contexto.update(detalle, turnos=len(_historial) // 2,
                         chars=sum(len(m["content"]) for m in base),
                         para=texto, dicho_al_modelo=para_modelo,
                         decision=None)
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
        # Si hubo web, ese pensamiento gana sobre lo que encontro el cache: lo
        # que define este turno no es de que trata la pregunta sino de donde
        # salio la respuesta. Es el mismo mecanismo que la iniciativa.
        # Cache acertado y sin web: el turno va a ser corto. El relleno pasa a
        # solo-ruidos y empieza mas tarde, asi en el caso tipico no suena nada.
        if hit and not web:
            relleno.poner_rapido()

        if web:
            hit, cacheado = None, pensamientos_semilla.PENSAMIENTO_WEB
        _contexto["pensamiento"] = (
            {"disparador": hit["disparador"], "sim": hit["sim"]} if hit
            else ({"disparador": "(web)", "sim": None} if web else None))
        emitir("contexto", **_contexto)

        salida = sin_pensamiento(_generar(base, pensamiento=cacheado,
                                          relleno=relleno))

        # Red contra el loro. Visto en vivo: a "nada, a ti que te gustaria
        # hacer" contesto PALABRA POR PALABRA lo mismo que al turno anterior,
        # con un razonamiento que ademas era correcto ("What would you like to
        # do?"). El `repeat_penalty` no lo agarra porque solo mira los ultimos
        # tokens y la respuesta anterior queda mas atras que su ventana.
        #
        # Se reintenta UNA vez y sin el pensamiento cacheado: si el cache
        # acerto en los dos turnos, el mismo arranque lo empuja al mismo lugar,
        # y darle otro empujon igual seria pedirle lo mismo esperando otra cosa.
        if salida and salida.strip().lower() == _ultima_del_bot().lower():
            emitir("nota", text="se repitio, lo intento de nuevo")
            salida = sin_pensamiento(_generar(base, pensamiento="",
                                              relleno=relleno))
        _contexto["decision"] = "hablar"
        emitir("contexto", **_contexto)

        if not propia:
            _historial.append({"role": "user", "content": texto})
        _historial.append({"role": "assistant", "content": salida})
        return _fin(salida, origen)
    finally:
        # Red de seguridad: si el turno murio por una excepcion, el locutor
        # nunca solto una frase y el relleno seguiria hablando solo para
        # siempre.
        relleno.cancelar()
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
                # `sin_pensamiento` NO es opcional aca. Sin el, prender el
                # modo thinking convirtio al consolidador en una maquina de
                # guardar basura: se archivaron como memorias el razonamiento
                # crudo ("The user writes in Spanish and I answer in Spanish"),
                # los encabezados del extractor ("The key points are:") y hasta
                # un "</think>" suelto. Y despues `_volatil()` se las inyectaba
                # de vuelta en cada turno como si fueran cosas sabidas.
                memoria_service.consolidar(
                    lambda msgs: sin_pensamiento(llm_service.generar(msgs)))
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
                tools=[])
