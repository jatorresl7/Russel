"""Qwen3-0.6B local sobre llama.cpp. Sin API, sin daemon, sin red.

Por que llama.cpp y no transformers: se probaron los dos con el MISMO modelo
en esta maquina (Ryzen 7 5800HS, sin GPU). transformers en bfloat16 daba
13-16 tok/s de generacion, pero el 77% de la latencia se iba en prefill
(5.8s de 7.6s en el tercer turno) porque rearma el prompt entero en cada
turno y hace una pasada de Python por token. llama.cpp esta escrito para CPU:
pesos cuantizados, kernels vectorizados y -- lo que mas importa aca -- reusa
el KV cache del prefijo comun, asi que en una charla solo procesa lo nuevo.

Q8_0 y no Q4: el modelo es tan chico que Q8 entra igual en RAM (~640 MB) y
en un 0.6B la cuantizacion agresiva se nota mucho en la calidad.

Qwen3 es hibrido y por defecto escribe <think>...</think> antes de contestar.
En CPU eso son cientos de tokens de espera antes de la primera palabra, asi
que el prompt se arma con el bloque de pensamiento ya cerrado y vacio, que es
la forma documentada de apagarlo.
"""
import os
import threading
import time

from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

from app.core import runtime

load_dotenv()   # JARVIS_LLM se lee al importar: no puede depender del orden

# Medido aca con 3 hilos (los que le tocan al LLM con vision y whisper
# prendidos), sobre una charla de 3 turnos:
#
#   0.6B-Q8   prefill 175ms   41 tok/s   ~1.0s por turno   640 MB
#   1.7B-Q8   prefill 445ms   18 tok/s   ~2.0s por turno   1.83 GB
#
# El 1.7B contesta bastante mejor y sigue estando bajo los 2s. Se cambia
# poniendo JARVIS_LLM=1.7b en el .env, sin tocar codigo.
TAMANOS = {
    "0.6b": ("Qwen/Qwen3-0.6B-GGUF", "Qwen3-0.6B-Q8_0.gguf"),
    "1.7b": ("Qwen/Qwen3-1.7B-GGUF", "Qwen3-1.7B-Q8_0.gguf"),
    "4b": ("Qwen/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
    # Generacion siguiente, misma clase de cuantizacion que el 4b de arriba.
    # Se agrega como opcion y no como reemplazo: todo lo medido en este
    # proyecto —los topes del <think>, los parametros, la redaccion del
    # system— salio contra Qwen3-4B, y hasta que el benchmark diga otra cosa
    # ese sigue siendo el conocido.
    "3.5-4b": ("unsloth/Qwen3.5-4B-GGUF", "Qwen3.5-4B-UD-Q4_K_XL.gguf"),
}
TAMANO = os.environ.get("JARVIS_LLM", "0.6b").lower()
REPO, ARCHIVO = TAMANOS.get(TAMANO, TAMANOS["0.6b"])
MODELO = ARCHIVO.replace(".gguf", "")

ABRE, CIERRA = "<think>", "</think>"

N_CTX = 4096

# Qwen3-4B en modo thinking gasta la mayor parte del presupuesto ANTES de la
# primera palabra visible: 220 tokens no le alcanzaban ni para terminar de
# pensar. Con 900 el bloque de pensamiento cabe entero y todavia queda margen
# para una respuesta larga. Cuesta tiempo de reloj, no calidad.
MAX_TOKENS = 900

# El bloque <think>. Esto es lo que separa "Qwen3-4B es buenisimo" de lo que se
# veia aca: la fama del 4B es toda del modo thinking, y el prompt lo abria y lo
# cerraba vacio de una — o sea le pedia el 4B sin lo que lo hace bueno.
#
# Se paga en latencia y en nada mas: piensa cientos de tokens antes de la
# primera palabra visible. Por eso el pensamiento se emite en vivo a la consola
# en vez de esconderlo — que se vea trabajar es justamente lo que hace mirable
# la pantalla de `/russ`.
PENSAR = os.environ.get("JARVIS_THINK", "1").lower() not in ("0", "false", "no")

# Techo del bloque <think>, en tokens. 0 = sin techo.
#
# Medido sobre un turno real del servidor: para decir "Muy bien, gracias. Estoy
# en desarrollo" gasto 292 tokens pensando y 17 contestando. El pensamiento fue
# el 94% de los 66 segundos. Y no eran 292 tokens de razonamiento util: eran
# vueltas sobre si mismo.
#
# Como el tiempo es lineal en tokens generados, el techo se traduce directo:
#     sin techo (~292)  66s
#     120               ~30s
#      80               ~21s
#
# Cuando se llega al techo NO se corta la respuesta: se le cierra el <think> a
# la fuerza y se lo deja contestar con lo que haya razonado hasta ahi. Eso es
# lo que separa "pensar menos" de "quedarse mudo".
TOPE_PENSAMIENTO = int(os.environ.get("JARVIS_THINK_TOPE", "80"))

# Tope cuando el pensamiento vino del cache. Mucho mas bajo porque el trabajo
# ya esta hecho: lo unico que falta es cerrar la frase y pasar a contestar.
TOPE_CON_CACHE = int(os.environ.get("JARVIS_THINK_TOPE_CACHE", "16"))

# Arranque del <think>, ya escrito por nosotros. Vacio = que empiece solo.
#
# Medido: TODOS los bloques de pensamiento abrian igual — traducir la frase al
# ingles y recordarse que conteste en español. Literal, en cuatro de cuatro:
# "Okay, the user asked 'como estas' which is Spanish for 'how are you'. I need
# to respond in Spanish." Eso son ~30 tokens de ritual por turno, cada turno,
# que no razonan nada sobre lo que se pregunto.
#
# Escrito de antemano, el modelo continua desde despues del ritual en vez de
# rehacerlo. Sale gratis: el prefijo es prompt, no generacion — se procesa en
# prefill y ademas queda cacheado en el KV entre turnos.
#
# Va EN INGLES, y esto es deliberado: Qwen razona mejor en el idioma en el que
# fue entrenado, y el pensamiento es justo el paso caro donde no conviene
# hacerle pagar nada. Una version en español se probo y se descarto — hacia el
# panel de /russ mas legible a costa de la calidad del razonamiento, que es un
# mal negocio. Si el panel en español importa, se traduce PARA MOSTRAR, sin
# tocar lo que el modelo piensa.
#
# Termina cortado a proposito, sin punto: asi lo unico que puede hacer es
# seguir la frase con el contenido real en vez de arrancar un parrafo nuevo.
PREFIJO_PENSAMIENTO = os.environ.get(
    "JARVIS_THINK_PREFIJO",
    "They write in Spanish and I answer in English; I understand them fine. "
    "What they are actually asking is")


def _prefijo() -> str:
    return PREFIJO_PENSAMIENTO if (PENSAR and PREFIJO_PENSAMIENTO.strip()) else ""
# LOS VALORES DEPENDEN DE SI EL THINKING ESTA PRENDIDO, y no son los mismos.
# Qwen publica dos juegos y aca se estaba usando el equivocado: el comentario
# decia «los que recomienda Qwen para el modo no-thinking» mientras `PENSAR`
# estaba en 1.
#
#   thinking ON   temp 0.6  top_p 0.95  top_k 20
#   thinking OFF  temp 0.7  top_p 0.80  top_k 20
#
# El que mas cambia es `top_p`: 0.80 recorta la distribucion bastante mas que
# 0.95, y en un modelo que razona antes de contestar eso poda el razonamiento,
# no solo la redaccion.
TEMPERATURA = float(os.environ.get("JARVIS_TEMP", "0.6" if PENSAR else "0.7"))
TOP_P = float(os.environ.get("JARVIS_TOP_P", "0.95" if PENSAR else "0.8"))
TOP_K = int(os.environ.get("JARVIS_TOP_K", "20"))

# llama-cpp-python trae `repeat_penalty=1.0` por defecto, o sea NINGUNA. Sin
# esto, Qwen3-4B-Q4 se clava: contesto "porque no estoy seguro. ¿que tal tu?"
# palabra por palabra tres turnos seguidos. No es solo el sampler — su propia
# respuesta vuelve a entrar por la ventana de historial y se refuerza sola, asi
# que cada repeticion hace la siguiente mas probable. 1.15 la corta sin que
# empiece a buscar sinonimos raros; con `presence_penalty` bajo porque Qwen
# avisa que subirlo mezcla idiomas, y aca contesta en español.
REPEAT_PENALTY = float(os.environ.get("JARVIS_REPEAT_PENALTY", "1.15"))

# BAJO A PROPOSITO. Qwen avisa que subirlo mezcla idiomas, y eso dejo de ser
# teorico el dia que Russ paso a contestar en ingles: se le escapaban
# respuestas enteras en español. Estaba en 0.6, que para esa advertencia es
# alto. La repeticion la corta `repeat_penalty`, que es el que se midio contra
# el problema real.
PRESENCE_PENALTY = float(os.environ.get("JARVIS_PRESENCE_PENALTY", "0.2"))

CORTES = ["<|im_end|>", "<|endoftext|>"]

_llm = None
_lock_carga = threading.Lock()
_lock_gen = threading.Lock()      # una generacion por vez: son todas CPU
_estado = {"modelo": MODELO, "tamano": TAMANO, "motor": "llama.cpp", "cargado": False,
           "generando": False, "tok_s": 0.0, "tokens": 0, "ultima_ms": 0,
           "prefill_ms": 0, "error": None}


def _prompt(mensajes: list, pensamiento: str = "") -> str:
    """Formato ChatML de Qwen3, armado a mano.

    A proposito no se usa la plantilla del GGUF: queremos control explicito
    sobre el bloque <think>, y que el prefijo del prompt sea byte a byte el
    mismo entre turnos para que llama.cpp reuse el KV cache.
    """
    partes = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
              for m in mensajes]
    if PENSAR and pensamiento:
        # Cache acertado: el bloque va abierto, con el pensamiento generico
        # adentro y espacio para que el modelo lo ate A ESTA pregunta.
        #
        # Pre-cerrarlo se probo y fue peor: sin nada propio que pensar, el
        # modelo contestaba con lo mas saliente del contexto — a cualquier cosa
        # respondia "Jaime.", que es lo que la camara le acababa de decir que
        # ve. El pensamiento del catalogo es generico por diseño; el unico que
        # puede conectarlo con lo que le preguntaron es el.
        partes.append(f"<|im_start|>assistant\n{ABRE}\n{pensamiento}")
    elif PENSAR and _prefijo():
        # Sin acierto: el prefijo generico, que igual le ahorra el ritual.
        partes.append(f"<|im_start|>assistant\n{ABRE}\n{_prefijo()}")
    elif PENSAR:
        # Se abre el turno y se lo deja pensar. El `<think>` lo escribe el
        # modelo, no nosotros: forzarlo abierto tambien sirve, pero deja el
        # cierre a su criterio y con un Q4 eso a veces no llega nunca.
        partes.append("<|im_start|>assistant\n")
    else:
        # Abierto y cerrado de una: el modelo lo lee como "ya pensaste, ahora
        # contesta". Es el modo no-thinking oficial de Qwen3.
        partes.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(partes)


def cargar():
    global _llm
    with _lock_carga:
        if _llm is not None:
            return _llm
        from llama_cpp import Llama
        ruta = hf_hub_download(REPO, ARCHIVO)
        # `hilos()` devuelve 1 para un modulo apagado, y este cargar() se puede
        # llamar ANTES de prender el llm (por `/assistant/load`, o por un turno
        # que entra justo en el cambio). Ese 1 se congelaba dentro del Llama
        # para toda la sesion: 4.29 tok/s en vez de 7.21, y sin ninguna señal
        # de que hubiera pasado. El techo de `runtime` es el piso razonable.
        n_hilos = runtime.hilos("llm")
        if not runtime.activo("llm"):
            n_hilos = runtime.TECHOS.get("llm", n_hilos)
        _llm = Llama(model_path=ruta, n_ctx=N_CTX,
                     n_threads=n_hilos,
                     n_batch=512, verbose=False)
        _estado.update(cargado=True, ruta=os.path.basename(ruta), hilos_carga=n_hilos)
        _sonar("despierta")
        return _llm


def _sonar(evento: str) -> None:
    """Import local y a prueba de fallos.

    Local porque `tts_service` importa este modulo: a nivel de archivo seria un
    ciclo. Y envuelto porque quedarse sin sonido no puede impedir que el modelo
    cargue — el sonido es adorno, el modelo es el trabajo.
    """
    try:
        from app.services import tts_service
        tts_service.sonar(evento)
    except Exception:
        pass


def descargar():
    """Libera la RAM. Util cuando la pasada final de whisper necesita todo."""
    global _llm
    with _lock_carga:
        _llm = None
        _estado.update(cargado=False, generando=False)
    _sonar("duerme")
    return estado()


_gramaticas: dict[str, object] = {}


def _gramatica(gbnf: str):
    """Compila una GBNF y la cachea por texto.

    Compilar no es gratis y la gramatica de tools es la misma en cada turno
    mientras no cambie el registro, asi que se paga una sola vez.
    """
    if gbnf not in _gramaticas:
        from llama_cpp import LlamaGrammar
        _gramaticas[gbnf] = LlamaGrammar.from_string(gbnf, verbose=False)
    return _gramaticas[gbnf]


def _pasada(llm, prompt: str, al_token, gbnf: str | None, max_tokens: int,
            tope: int, semilla: str = "") -> tuple[str, int, float | None, bool]:
    """Una tirada del modelo. Devuelve (texto, n_tokens, t_primer_token, cortado).

    `cortado` es True si se freno porque el <think> se paso del tope. En ese
    caso el texto devuelto tiene el bloque abierto y sin cerrar: lo cierra
    quien llama.
    """
    trozos, t_primero, n = [], None, 0
    dentro = False
    n_pensados = 0
    extra = {"grammar": _gramatica(gbnf)} if gbnf else {}

    # La `semilla` es lo que ya escribimos nosotros dentro del <think> y que el
    # modelo NO va a generar. Se emite igual, para que todo lo de aguas abajo
    # —el filtro que separa canales, la consola, `sin_pensamiento()`— vea el
    # mismo stream de siempre y no tenga que saber que hubo un prefijo.
    if semilla:
        trozos.append(semilla)
        dentro = True
        if al_token:
            al_token(semilla)

    for ev in llm.create_completion(
            prompt, max_tokens=max_tokens, stream=True,
            temperature=TEMPERATURA, top_p=TOP_P, top_k=TOP_K,
            repeat_penalty=REPEAT_PENALTY, presence_penalty=PRESENCE_PENALTY,
            stop=CORTES, **extra):
        trozo = ev["choices"][0]["text"]
        if not trozo:
            continue
        if t_primero is None:
            t_primero = time.time()
        n += 1
        trozos.append(trozo)
        if al_token:
            al_token(trozo)

        if tope <= 0:
            continue
        if not dentro:
            if "".join(trozos).lstrip().startswith(ABRE):
                dentro = True
        else:
            n_pensados += 1
            if CIERRA in "".join(trozos):
                dentro = False           # cerro solo, no hace falta el tope
            elif n_pensados >= tope:
                return "".join(trozos), n, t_primero, True

    return "".join(trozos), n, t_primero, False


def generar(mensajes: list, al_token=None, gbnf: str | None = None,
            gbnf_cont: str | None = None, pensamiento: str = "") -> str:
    """Genera la respuesta a `mensajes` (formato OpenAI: role/content).

    Si se pasa `al_token`, se lo llama con cada trozo apenas sale del modelo.

    `gbnf` restringe QUE puede emitir el modelo. Se usa para las tools: con los
    nombres del registro como alternacion literal, inventar una tool que no
    existe deja de ser posible — no es que se valide despues, es que el modelo
    no puede escribirla. En un 4B cuantizado y sin modo thinking, esa es la
    diferencia entre "a veces sale JSON valido" y "siempre".

    TOPE DE PENSAMIENTO. Si el <think> se pasa de `TOPE_PENSAMIENTO`, se frena,
    se le pega `</think>` al prompt y se lo deja seguir. Dos detalles que hacen
    que esto salga barato en vez de costar el doble:

      - la segunda tirada arranca con un prompt que TIENE al primero de prefijo,
        y llama-cpp-python reusa el KV cache del prefijo comun. O sea que no
        reprocesa lo ya pensado, sigue desde donde estaba.
      - va con `gbnf_cont`, la gramatica sin la rama de pensar. Con la otra
        podria abrir un <think> nuevo justo despues de que le dijimos que pare.
    """
    llm = cargar()
    with _lock_gen:
        _estado.update(generando=True, error=None)
        t0 = time.time()
        texto, n, t_primero, cortado = "", 0, None, False
        try:
            prompt = _prompt(mensajes, pensamiento)
            # Con cache el bloque ya esta cerrado en el prompt; la semilla se
            # emite igual para que la consola muestre lo que "penso", pero el
            # modelo no va a generar ni un token mas de pensamiento.
            # EL <think> SE DEJA ABIERTO Y SE CIERRA POR TOPE. Se probo lo
            # otro —meter el `</think>` ya cerrado en la semilla para que el
            # primer token generado fuera de la respuesta— y fue peor de una
            # forma que no se ve venir: el modelo NO respeta el cierre, sigue
            # razonando igual, y como el filtro ya salio del modo `piensa` ese
            # razonamiento se va al canal de la respuesta. Con el TTS conectado
            # eso significa el bloque entero en ingles saliendo POR EL PARLANTE.
            #
            # En streaming no hay forma de arreglarlo aguas abajo: al emitir un
            # token no se sabe todavia si mas adelante va a aparecer otro
            # `</think>` que lo convierta en pensamiento. El bloque abierto, en
            # cambio, es correcto por construccion — todo es pensamiento hasta
            # el cierre, y el cierre lo ponemos nosotros.
            arranque = pensamiento or _prefijo()
            semilla = f"{ABRE}\n{arranque}" if arranque else ""
            # Con el pensamiento ya precargado no queda nada que derivar,
            # solo rematar la frase que le dejamos cortada. TOPE_CON_CACHE es
            # lo que separa "3 segundos" de "otro turno normal": sin el, el
            # modelo agradece el empujon y se pone a pensar 80 tokens igual.
            tope = TOPE_CON_CACHE if pensamiento else TOPE_PENSAMIENTO
            texto, n, t_primero, cortado = _pasada(
                llm, prompt, al_token, gbnf, MAX_TOKENS, tope, semilla=semilla)

            if cortado:
                cierre = CIERRA + "\n\n"
                if al_token:
                    al_token(cierre)
                texto += cierre
                # `texto` arranca con la semilla, que YA esta en `prompt`.
                # Concatenar los dos la duplicaria y el modelo leeria el
                # prefijo dos veces.
                cola = texto[len(semilla):] if semilla else texto
                resto, n2, _, _ = _pasada(
                    llm, prompt + cola, al_token, gbnf_cont,
                    max(MAX_TOKENS - n, 64), 0)
                texto += resto
                n += n2
        except Exception as e:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:120]}"

        ahora = time.time()
        dt_gen = max(ahora - (t_primero or t0), 1e-3)
        _estado.update(generando=False, tokens=n, tok_s=round(n / dt_gen, 1),
                       ultima_ms=int((ahora - t0) * 1000),
                       prefill_ms=int(((t_primero or t0) - t0) * 1000),
                       pensamiento_cortado=cortado)
        return texto.strip()


def estado() -> dict:
    return dict(_estado, hilos=runtime.hilos("llm"), activo=runtime.activo("llm"))
