"""La voz de Russ: Piper local, y los sonidos que hace cuando no habla.

POR QUE PIPER Y NO UN TTS EN LA NUBE. Todo lo demas de Russ corre en esta
maquina y sin red; mandar cada frase a un servidor seria el unico punto del
sistema que deja de funcionar cuando se cae internet — que hoy mismo se cayo.
Piper sintetiza en CPU en decimas de segundo y no pregunta nada a nadie.

SE HABLA POR FRASE, NO POR RESPUESTA. Esta es la decision que importa. El LLM
escupe tokens a ~7/s, asi que esperar la respuesta entera para empezar a hablar
sumaria toda la generacion a la espera. En cambio se corta en cada punto y se
manda esa frase al parlante mientras el modelo sigue escribiendo la siguiente:
el audio arranca despues de la PRIMERA frase, no de la ultima, y a partir de
ahi la sintesis va por detras de la generacion sin que se note.

LA COLA ES DE UN SOLO HILO. Dos frases sonando encima serian ininteligibles,
asi que hay una cola y un reproductor que la vacia en orden. Sintetizar es lo
caro y se hace dentro de ese hilo: si se hiciera en el hilo del LLM le estaria
robando CPU justo al que la necesita.
"""
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import wave

from app.core import runtime
from app.db import SessionLocal, Marcador
from app.services import robotico

DIR_VOCES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "voces")
DIR_SONIDOS = os.path.join(os.path.dirname(DIR_VOCES), "sonidos")

CLAVE_VOZ = "tts_voz"
CLAVE_VOL = "tts_volumen"
CLAVE_PRESET = "tts_robot"
CLAVE_FONEMAS = "tts_fonemas"
CLAVE_PARAMS = "tts_params"
CLAVE_AJUSTES = "tts_robot_ajustes"

# Los momentos en los que Russ puede sonar sin hablar. El nombre del evento es
# el nombre del archivo: `sonidos/pensando.wav`. Que sea por convencion y no
# por una tabla es a proposito — copiar un wav a la carpeta lo da de alta.
EVENTOS = {
    "despierta":  "cuando se prende el modelo",
    "pensando":   "mientras piensa, antes de la primera palabra",
    "escuchando": "cuando el microfono detecta que empezaste a hablar",
    "eureka":     "justo antes de empezar a contestar",
    "listo":      "cuando termina de contestar",
    "error":      "cuando algo falla",
    "duerme":     "cuando se apaga el modelo",
}

# Reproductor. `paplay` primero porque esta maquina es PipeWire; los otros
# quedan de respaldo para que esto no dependa del servidor de audio del dia.
REPRODUCTORES = (["paplay"], ["pw-play"], ["aplay", "-q"])

_voz = None                 # PiperVoice cargada
_voz_nombre = None
_lock = threading.Lock()
# DOS COLAS Y DOS HILOS, no uno. La primera lleva lo que hay que decir; la
# segunda, wavs ya listos para sonar.
#
# Con un solo hilo cada frase era: sintetizar (~300 ms) y recien ahi sonar. Ese
# hueco se pagaba en TODAS las frases, no solo en la primera, y es silencio
# puro en medio de una respuesta hablada. Separando los dos trabajos, mientras
# suena la frase N se esta sintetizando la N+1, y el hueco desaparece salvo en
# la primera de todas.
#
# Y es lo que hace util al `eureka`: suena mientras Piper sintetiza la primera
# frase, asi que esos 300 ms dejan de ser espera y pasan a ser el bip.
_cola = queue.Queue()         # entra texto o wav: lo que hay que decir
_cola_audio = queue.Queue()   # sale wav listo: lo que hay que reproducir
_proc = None                # el reproductor corriendo, para poder matarlo
_lock_proc = threading.Lock()
# `dichas` cuenta frases y `sonados` cuenta blips: separados porque son cosas
# distintas y porque sin el segundo no habia forma de comprobar que un evento
# habia sonado — la unica señal era escucharlo.
_estado = {"hablando": False, "dichas": 0, "sonados": 0, "error": None,
           "ultimo": "", "ultimo_sonido": ""}


# ------------------------------------------------------------------ catalogo

def voces() -> list:
    """Las voces que hay bajadas. Una voz de Piper son dos archivos: el .onnx
    y su .onnx.json; sin el json no se puede cargar, asi que se ignora."""
    if not os.path.isdir(DIR_VOCES):
        return []
    salida = []
    for f in sorted(os.listdir(DIR_VOCES)):
        if not f.endswith(".onnx"):
            continue
        if not os.path.exists(os.path.join(DIR_VOCES, f + ".json")):
            continue
        nombre = f[:-len(".onnx")]
        partes = nombre.split("-")
        salida.append({
            "nombre": nombre,
            "idioma": partes[0] if partes else "",
            "quien": partes[1] if len(partes) > 1 else "",
            "calidad": partes[2] if len(partes) > 2 else "",
            "mb": round(os.path.getsize(os.path.join(DIR_VOCES, f)) / 1e6, 1),
            "activa": nombre == voz_actual(),
            "rota": nombre in _rotas,
            # Una voz que no es española igual habla español: se fonemiza
            # aparte. Se marca solo para que se entienda de donde sale el
            # timbre, no como advertencia.
            "extranjera": not partes[0].startswith("es") if partes else False,
        })
    return salida


def _marca(clave: str, defecto=None):
    db = SessionLocal()
    try:
        m = db.get(Marcador, clave)
        return m.valor if m and m.valor else defecto
    except Exception:
        return defecto
    finally:
        db.close()


def _poner(clave: str, valor: str) -> None:
    db = SessionLocal()
    try:
        m = db.get(Marcador, clave)
        if m:
            m.valor = valor
        else:
            db.add(Marcador(clave=clave, valor=valor))
        db.commit()
    finally:
        db.close()


def voz_actual() -> str | None:
    """La elegida, o la primera que haya. Sin el respaldo, una instalacion
    nueva quedaria muda hasta que alguien entre al panel a elegir."""
    guardada = _marca(CLAVE_VOZ)
    if guardada and os.path.exists(os.path.join(DIR_VOCES, guardada + ".onnx")):
        return guardada
    if not os.path.isdir(DIR_VOCES):
        return None
    for f in sorted(os.listdir(DIR_VOCES)):
        if f.endswith(".onnx"):
            return f[:-len(".onnx")]
    return None


def elegir(nombre: str) -> dict:
    ruta = os.path.join(DIR_VOCES, nombre + ".onnx")
    if not os.path.exists(ruta):
        return {"ok": False, "motivo": "esa voz no esta bajada"}
    _poner(CLAVE_VOZ, nombre)
    global _voz, _voz_nombre
    with _lock:
        _voz, _voz_nombre = None, None      # que la recargue la proxima
    return {"ok": True, "voz": nombre}


def volumen(v: int | None = None) -> int:
    if v is not None:
        _poner(CLAVE_VOL, str(max(0, min(150, int(v)))))
    try:
        return int(_marca(CLAVE_VOL, "100"))
    except (TypeError, ValueError):
        return 100


# ------------------------------------------------------------------ sintesis

_rotas: set = set()

# El idioma con el que se FONEMIZA, que no tiene por que ser el de la voz.
#
# Piper convierte texto a fonemas con espeak-ng y despues el modelo convierte
# fonemas en audio. Los dos pasos son independientes, asi que se puede pisar el
# idioma del primero: una voz inglesa fonemizando en español dice español
# correcto, con su timbre.
#
# Medido con en_US-lessac-medium sobre "Hola Jaime, soy Russ. El niño y la
# jirafa corren rapido":
#     reglas inglesas   ˈoʊlæ dʒˈeɪm, sˈɔɪ ɹˈʌs.
#     reglas españolas  ˈola xˈaɪme, sˈoɪ rˈuss.
# y CERO fonemas fuera del mapa del modelo — el inventario ingles cubre los del
# español, jota y erre vibrante incluidas.
#
# Esto importa porque en español solo hay 9 voces de Piper en total. Con esto
# el catalogo entero queda disponible, que es la unica forma real de encontrar
# una que guste.
FONEMAS_POR_DEFECTO = "es"


def idioma_fonemas(nuevo: str | None = None) -> str:
    global _voz
    if nuevo is not None:
        _poner(CLAVE_FONEMAS, nuevo)
        with _lock:
            _voz = None            # que se recargue con el idioma nuevo
    return _marca(CLAVE_FONEMAS, FONEMAS_POR_DEFECTO)


# Nombres que espeak-ng acepta de verdad. NO son los del nombre del archivo:
# la voz se llama `en_GB-semaine-medium` pero espeak no conoce "en-gb" ni
# "en-GB" ni "en_GB" — solo "en". Poner uno invalido tira `Failed to set voice`
# recien al fonemizar, o sea en mitad de la primera frase.
IDIOMAS = {
    "es": "español",
    "es-419": "español latinoamericano",
    "en": "ingles",
    "pt": "portugues",
    "fr": "frances",
    "it": "italiano",
    "de": "aleman",
}


def _forzar_idioma(voz) -> None:
    """Pisa el `espeak_voice` del modelo recien cargado, si es valido.

    Se hace al cargar y no por frase porque `phonemize` lee la config del
    objeto: una vez alcanza y no cuesta nada.

    Se PRUEBA antes de dejarlo puesto. Un codigo invalido no falla al asignar,
    falla al fonemizar — o sea en mitad de la primera frase y con un error que
    no menciona el idioma. Mejor descubrirlo aca y volver al de la voz.
    """
    idioma = idioma_fonemas()
    if not idioma or idioma == "auto":
        return
    previo = getattr(voz.config, "espeak_voice", None)
    try:
        voz.config.espeak_voice = idioma
        voz.phonemize("hola")            # si el codigo no existe, revienta aca
    except Exception as e:
        try:
            voz.config.espeak_voice = previo
        except Exception:
            pass
        _estado["error"] = (f"idioma de fonemas '{idioma}' invalido "
                            f"({type(e).__name__}); uso el de la voz")


def _cargar():
    """Carga perezosa y cacheada: el .onnx tarda ~1 s en abrir y no tiene
    sentido pagarlo por frase.

    Si el archivo esta cortado —una descarga interrumpida deja un .onnx a
    medias que pesa casi lo correcto— onnxruntime tira INVALID_PROTOBUF. Eso
    paso de verdad y dejo a Russ mudo con un error que no dice que hacer. Aca
    se marca esa voz como rota y se sigue con la siguiente que cargue: quedarse
    sin voz por un archivo malo, teniendo cinco sanas al lado, seria absurdo.
    """
    global _voz, _voz_nombre
    from piper import PiperVoice

    nombre = voz_actual()
    if _voz is not None and _voz_nombre == nombre and nombre not in _rotas:
        return _voz

    candidatas = [nombre] + [v["nombre"] for v in voces()] if nombre else \
                 [v["nombre"] for v in voces()]
    for cand in candidatas:
        if not cand or cand in _rotas:
            continue
        try:
            _voz = PiperVoice.load(os.path.join(DIR_VOCES, cand + ".onnx"))
            _forzar_idioma(_voz)
            _voz_nombre = cand
            if cand != nombre:
                _estado["error"] = f"{nombre} esta rota, uso {cand}"
            return _voz
        except Exception as e:
            _rotas.add(cand)
            _estado["error"] = (f"{cand} no carga ({type(e).__name__}). "
                                "Borrala de voces/ y volve a bajarla.")
    raise RuntimeError("no hay ninguna voz que cargue en voces/")


def robot(preset: str | None = None, ajustes: dict | None = None) -> dict:
    """Lee o guarda el timbre robotico. Sin argumentos, solo lee."""
    if preset is not None:
        _poner(CLAVE_PRESET, preset)
    if ajustes is not None:
        _poner(CLAVE_AJUSTES, json.dumps(ajustes))
    guardado = _marca(CLAVE_PRESET, robotico.POR_DEFECTO)
    try:
        extra = json.loads(_marca(CLAVE_AJUSTES) or "{}")
    except ValueError:
        extra = {}
    # Los limites viajan con la respuesta para que el panel no tenga una copia
    # que se desincronice: los rangos son parte del contrato, no decoracion.
    return {"preset": guardado, "ajustes": extra,
            "efectivo": robotico.config(guardado, extra),
            "presets": list(robotico.PRESETS),
            "limites": {k: {"min": lo, "max": hi}
                        for k, (lo, hi) in robotico.LIMITES.items()},
            "base": {p: dict(v) for p, v in robotico.PRESETS.items()}}


# Todo lo que expone `piper.SynthesisConfig`, con el rango util de cada uno.
# `defecto=None` significa "lo que traiga la voz": cada modelo viene con sus
# propios valores y pisarlos con un numero fijo empeora las que ya estaban bien.
PARAMS = {
    "speaker_id": {
        "min": 0, "max": 0, "paso": 1, "defecto": None,
        "que": "cual de las voces del modelo. Varios modelos traen mas de una "
               "—semaine trae 4— y suenan distinto de verdad, no es un matiz"},
    "length_scale": {
        "min": 0.5, "max": 2.0, "paso": 0.05, "defecto": None,
        "que": "duracion. Mas de 1 habla mas lento, y es lo PRIMERO que hay "
               "que mover si se le entienden mal algunas palabras: casi "
               "siempre es que las dice demasiado rapido, no que la voz sea "
               "mala. Menos de 1 acelera y de paso baja la latencia"},
    "noise_scale": {
        "min": 0.0, "max": 1.2, "paso": 0.02, "defecto": None,
        "que": "variacion del timbre. Bajarlo la deja mas plana y mas nitida; "
               "subirlo la hace mas expresiva y menos predecible"},
    "noise_w_scale": {
        "min": 0.0, "max": 1.5, "paso": 0.02, "defecto": None,
        "que": "variacion de cuanto dura cada fonema. Bajarlo emparaja el "
               "ritmo, que ayuda a entender; subirlo suena mas humano y mas "
               "descuidado"},
    "volume": {
        "min": 0.1, "max": 2.0, "paso": 0.05, "defecto": 1.0,
        "que": "ganancia antes de los efectos. Distinto del volumen del "
               "reproductor: este entra a la cadena, aquel no"},
}


def params(voz: str | None = None, nuevos: dict | None = None) -> dict:
    """Los parametros de sintesis, POR VOZ.

    Por voz y no globales porque `speaker_id` no significa nada fuera de su
    modelo —semaine tiene 4 y davefx 1— y porque el `length_scale` que arregla
    una voz arruina otra. Guardar uno solo obligaria a reajustar cada vez que
    se cambia de voz.
    """
    voz = voz or voz_actual() or ""
    try:
        todos = json.loads(_marca(CLAVE_PARAMS) or "{}")
    except ValueError:
        todos = {}
    if nuevos is not None:
        todos[voz] = {k: v for k, v in nuevos.items()
                      if k in PARAMS and v is not None}
        _poner(CLAVE_PARAMS, json.dumps(todos))
        global _voz
        with _lock:
            _voz = None
    return todos.get(voz, {})


def _sintesis_cfg(voz_obj, extra: dict | None = None):
    """Arma el SynthesisConfig. Lo que no este puesto no se manda, para que
    piper use el default de la voz en vez de uno nuestro."""
    from piper import SynthesisConfig
    cfg = dict(params())
    if extra:
        cfg.update({k: v for k, v in extra.items()
                    if k in PARAMS and v is not None})
    if not cfg:
        return None
    kw = {}
    for k in ("length_scale", "noise_scale", "noise_w_scale", "volume"):
        if cfg.get(k) is not None:
            kw[k] = float(cfg[k])
    if cfg.get("speaker_id") is not None:
        n = getattr(voz_obj.config, "num_speakers", 1) or 1
        kw["speaker_id"] = max(0, min(n - 1, int(cfg["speaker_id"])))
    return SynthesisConfig(**kw) if kw else None


def _a_wav(texto: str, preset: str | None = None,
           ajustes: dict | None = None, sint: dict | None = None) -> str:
    """Sintetiza y le pasa la cadena de robot por encima.

    Piper escribe el wav; despues se relee, se procesa y se reescribe. Suena a
    ida y vuelta innecesaria pero no lo es: `synthesize_wav` quiere un objeto
    wave y devolver muestras crudas obligaria a replicar su manejo de la
    configuracion de cada voz. El archivo esta en /tmp y son decimas de ms.
    """
    import numpy as np

    voz = _cargar()
    fd, ruta = tempfile.mkstemp(suffix=".wav", prefix="russ-")
    os.close(fd)
    try:
        with wave.open(ruta, "wb") as w:
            voz.synthesize_wav(texto, w, syn_config=_sintesis_cfg(voz, sint))
    except Exception:
        # Si la sintesis falla, el `wave` a medio escribir tira al cerrarse un
        # "# channels not specified" que TAPA la causa real. Paso por aca por
        # un codigo de idioma invalido y el error que se veia no mencionaba el
        # idioma por ningun lado. Se borra el temporal y se deja subir la
        # excepcion de verdad.
        try:
            os.unlink(ruta)
        except OSError:
            pass
        raise

    r = robot()
    cfg = robotico.config(preset if preset is not None else r["preset"],
                          ajustes if ajustes is not None else r["ajustes"])
    if (cfg.get("anillo_mix") or cfg.get("drive") or cfg.get("eco_mix")
            or cfg.get("bits") or abs(float(cfg.get("tono", 1) or 1) - 1) > 0.01
            or abs(float(cfg.get("formante", 1) or 1) - 1) > 0.01):
        with wave.open(ruta, "rb") as w:
            sr, canales, ancho = w.getframerate(), w.getnchannels(), w.getsampwidth()
            crudo = w.readframes(w.getnframes())
        if ancho == 2:
            x = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
            y = robotico.aplicar(x, sr, cfg)
            with wave.open(ruta, "wb") as w:
                w.setnchannels(canales)
                w.setsampwidth(ancho)
                w.setframerate(sr)
                w.writeframes(np.clip(y * 32767, -32767, 32767)
                              .astype("<i2").tobytes())
    return ruta


def _reproducir(ruta: str) -> None:
    """Reproduce y se queda esperando, pero con el proceso a mano.

    `Popen` y no `run` para poder matarlo desde afuera: sin eso, `parar()` solo
    podria vaciar la cola y habria que aguantar hasta el final la frase que ya
    estaba sonando — que es justo la que molesta cuando se esta probando voces.
    """
    global _proc
    vol = volumen()
    for cmd in REPRODUCTORES:
        try:
            args = list(cmd)
            if cmd[0] == "paplay" and vol != 100:
                # paplay toma el volumen en escala 0..65536.
                args += ["--volume", str(int(65536 * vol / 100))]
            with _lock_proc:
                _proc = subprocess.Popen(args + [ruta],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
            try:
                _proc.wait(timeout=120)
            finally:
                with _lock_proc:
                    _proc = None
            return
        except FileNotFoundError:
            continue                      # ese reproductor no esta instalado
        except Exception as e:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:60]}"
            return
    _estado["error"] = "no hay con que reproducir (paplay/pw-play/aplay)"


def parar() -> dict:
    """Calla a Russ ya: vacia la cola y mata lo que este sonando.

    Existe por el probador. Al comparar voces se hacen diez clics en veinte
    segundos, y con una cola FIFO eso son diez frases encoladas sonando una
    tras otra mucho despues de que uno dejo de tocar. Probar tiene que
    REEMPLAZAR lo anterior, no formarse detras.
    """
    n = 0
    for cola in (_cola, _cola_audio):
        while True:
            try:
                item = cola.get_nowait()
                # Los wav de texto que ya estaban sintetizados se borran: si no,
                # cada vez que se corta una respuesta larga quedan diez
                # temporales de 100 KB en /tmp.
                if cola is _cola_audio and item and item[0] == "texto":
                    try:
                        os.unlink(item[1])
                    except OSError:
                        pass
                cola.task_done()
                n += 1
            except queue.Empty:
                break
    with _lock_proc:
        if _proc is not None and _proc.poll() is None:
            try:
                _proc.terminate()
            except Exception:
                pass
    return {"ok": True, "descartadas": n}


def _sintetizador():
    """Convierte texto en wav y lo pasa al reproductor. No suena nada aca.

    Va adelantado a proposito: apenas termina un wav lo encola y agarra el
    siguiente, sin esperar a que suene. Ese adelanto es lo que tapa el costo de
    la sintesis.
    """
    while True:
        item = _cola.get()
        try:
            if item is None:
                continue
            tipo, dato = item[0], item[1]
            if tipo == "texto":
                preset = item[2] if len(item) > 2 else None
                ajustes = item[3] if len(item) > 3 else None
                sint = item[4] if len(item) > 4 else None
                ruta = _a_wav(dato, preset, ajustes, sint)
                _cola_audio.put(("texto", ruta, dato))
            else:
                _cola_audio.put(("wav", dato, None))
        except Exception as e:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        finally:
            _cola.task_done()


def _reproductor():
    """El unico hilo que habla. Solo reproduce: lo caro ya lo hizo el otro."""
    while True:
        tipo, ruta, texto = _cola_audio.get()
        try:
            _estado["hablando"] = True
            _reproducir(ruta)
            if tipo == "texto":
                _estado["dichas"] += 1
                _estado["ultimo"] = (texto or "")[:120]
                try:
                    os.unlink(ruta)      # los de texto son temporales
                except OSError:
                    pass
            else:
                _estado["sonados"] += 1
                _estado["ultimo_sonido"] = os.path.basename(ruta)[:-4]
        except Exception as e:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        finally:
            _estado["hablando"] = not (_cola_audio.empty() and _cola.empty())
            _cola_audio.task_done()


threading.Thread(target=_sintetizador, daemon=True, name="russ-sintesis").start()
threading.Thread(target=_reproductor, daemon=True, name="russ-voz").start()


# -------------------------------------------------------------------- hablar

# Un corte de frase. Se exige un espacio o el final despues del signo para no
# partir en "3.5" ni en "es_ES-davefx-medium".
CORTE = re.compile(r'(?<=[.!?…])\s+|(?<=[.!?…])$')
MINIMO = 12          # caracteres. Mandar "Si." sola al parlante suena picado.


# Markdown que hay que sacar antes de hablar.
#
# El prompt dice "no lists, no markdown, no emojis" y aun asi lo mete: visto en
# vivo, "The **Gauss bell** refers to the **normal distribution**". Un modelo
# chico no obedece una prohibicion de formato de manera confiable, y el asterisco
# leido en voz alta arruina la frase entera.
#
# Se limpia ACA y no en el prompt porque en el prompt ya se intento y falla, y
# porque la consola SI deberia poder mostrar el markdown si algun dia se quiere.
# Lo que no puede es salir por el parlante.
_MD = [
    (re.compile(r'```.*?```', re.S), ' '),        # bloques de codigo
    (re.compile(r'`([^`]*)`'), r'\1'),            # codigo en linea
    (re.compile(r'\*\*([^*]+)\*\*'), r'\1'),     # negrita
    (re.compile(r'(?<!\w)\*([^*\n]+)\*(?!\w)'), r'\1'),   # cursiva
    (re.compile(r'(?<!\w)_([^_\n]+)_(?!\w)'), r'\1'),       # cursiva con _
    (re.compile(r'^\s{0,3}#{1,6}\s*', re.M), ''),             # titulos
    (re.compile(r'^\s{0,3}[-*+]\s+', re.M), ''),              # vinetas
    (re.compile(r'^\s{0,3}>\s*', re.M), ''),                  # citas
    (re.compile(r'\[([^\]]+)\]\([^)]*\)'), r'\1'),          # links
    (re.compile(r'^\s*[-=_]{3,}\s*$', re.M), ''),             # separadores
]


def limpiar_para_voz(texto: str) -> str:
    """Saca el markdown. Lo que queda es lo que se puede leer en voz alta."""
    t = texto or ""
    for patron, reemplazo in _MD:
        t = patron.sub(reemplazo, t)
    return " ".join(t.split())


def decir(texto: str, preset: str | None = None,
          ajustes: dict | None = None, sint: dict | None = None,
          prueba: bool = False) -> dict:
    """`preset`, `ajustes` y `sint` sirven para PROBAR sin guardar.

    `prueba=True` ademas CORTA lo que estuviera sonando o esperando. Las frases
    de la conversacion se encolan —hay que oirlas todas y en orden— pero las
    del probador se pisan: quien esta comparando voces quiere oir la ultima que
    toco, no las nueve anteriores.
    """
    texto = limpiar_para_voz(texto).strip()
    if not texto:
        return {"ok": False, "motivo": "vacio"}
    if not runtime.activo("tts"):
        return {"ok": False, "motivo": "el modulo tts esta apagado"}
    if prueba:
        parar()
    _cola.put(("texto", texto, preset, ajustes, sint))
    return {"ok": True, "encolado": True, "prueba": prueba}


def sonar(evento: str, prueba: bool = False) -> dict:
    """Un sonido corto por evento. Si no hay archivo para ese evento no pasa
    nada: los sonidos son opcionales por diseño, no una dependencia."""
    if not runtime.activo("tts"):
        return {"ok": False, "motivo": "apagado"}
    ruta = os.path.join(DIR_SONIDOS, evento + ".wav")
    if not os.path.exists(ruta):
        return {"ok": False, "motivo": "sin sonido para " + evento}
    if prueba:
        parar()
    _cola.put(("wav", ruta))
    return {"ok": True}


# ---------------------------------------------------------------- relleno

# Lo que dice mientras piensa. En ingles porque es lo que habla, y CORTAS
# porque tienen que caber enteras antes de que llegue la primera frase de la
# respuesta: una de diez palabras se pisaria con lo que viene.
#
# La mezcla de frase y ruido es a proposito. Solo bips cansa y no dice nada;
# solo frases suena a excusa de call center. Alternadas, la espera se siente
# como alguien ocupado y no como una barra de progreso.
# Ruidos, separados de las frases y COMPARTIDOS entre todos los modos. Un
# "Bzzt" sirve igual pensando que buscando; una frase no.
#
# Se dicen por el TTS y no son wavs a proposito: dichos por la misma voz que
# habla suenan a que el ruido lo hace el, y no a que le suena algo adentro. Es
# lo que hace BMO, que dice "beep boop" en vez de emitir un beep.
ONOMATOPEYAS = [
    "Bzzt.",
    "Beep boop.",
    "Bip. Bip.",
    "Beep.",
    "Hmm.",
    "Hmm hmm.",
    "Brr.",
    "Tick. Tick.",
    "Bzz.",
    "Boop.",
    "Beep. Beep. Boop.",
    "Mmm.",
    "Bip.",
    "Whirr.",
]

# Las frases, por modo. Sin onomatopeyas adentro: el ritmo las intercala.
FRASES = {
    "pensando": [
        "Let me think.",
        "Give me a second.",
        "Hold on.",
        "Working on it.",
        "Thinking.",
        "One moment.",
        "Almost.",
        "This one is not obvious.",
        "That is a good one.",
        "Nobody asked me that before.",
        "Let me get this right.",
        "I want to answer this properly.",
        "Turning it over.",
        "Hold that thought.",
        "This is taking me longer than I expected.",
        "Still here.",
        "I am slow today.",
        "My processor is doing its best.",
        "Do not go anywhere.",
        "I am not stuck, I promise.",
        "Nearly there.",
        "Give me one more second.",
        "Let me put this together.",
        "There is more to this than I thought.",
        "Interesting question, actually.",
        "I have half an answer.",
        "Just a moment more.",
        "This is the slow part.",
        "I am getting there.",
        "Wait, I have something.",
    ],
    "buscando": [
        "I do not know this one. Let me look it up.",
        "Going online for this.",
        "Hold on, I am looking that up.",
        "This one I have to go find.",
        "That is not something I know. Searching.",
        "Let me go and see.",
        "Reading about it now.",
        "Pulling this from outside.",
        "Consulting the internet.",
        "I am asking around.",
        "This is not mine to know.",
        "Looking it up properly.",
        "Fetching.",
        "This needs the internet.",
        "Somebody out there knows this.",
        "I would rather check than guess.",
    ],
    "mirando": [
        "Let me look properly.",
        "Focusing.",
        "Hold on, I am looking.",
        "Checking what is in front of me.",
        "Let me see that again.",
        "I am looking at it now.",
        "I want to be sure of what I see.",
        "Looking.",
        "Give me a moment with this.",
        "I want to describe it right.",
    ],
    "recordando": [
        "I know something about this.",
        "Wait, you told me about this.",
        "Let me remember.",
        "This rings a bell.",
        "I have this written down somewhere.",
        "Hold on, I remember something.",
        "Going back through what you told me.",
        "Searching my own head.",
        "I did keep this.",
        "You told me once. Let me get it right.",
        "Remembering.",
    ],
}

# EL RITMO. Que dice en cada vuelta, en orden. `None` = el wav `pensando`.
#
# Empieza con un ruido porque a los 3 s todavia no hay nada que explicar y una
# frase seria adelantarse. Despues alterna ruido y frase, que es como suena
# alguien ocupado y no un contestador. Y a partir de la quinta vuelta —treinta
# y pico de segundos— deja de hablar: a esa altura las palabras ya se
# repitieron bastante y cansan, mientras que un pitido cada tanto se tolera
# indefinidamente. Es tambien lo mas barato: el wav no pasa por el sintetizador.
RITMO = ["ruido", "frase", "ruido", "frase", "ruido", None]

# El ritmo de los turnos RAPIDOS: cuando el cache de pensamientos acerta, la
# respuesta empieza a hablar a los 3-4 s. Una frase de relleno ahi sobra o —
# peor— se encola justo antes de la primera frase real y la retrasa. Un solo
# ruido corto es todo lo que cabe, y si aun asi la cosa se estira, los bips.
RITMO_RAPIDO = ["ruido", None]

# Y arranca mas tarde que el normal, por lo mismo: a los 3 s el turno con cache
# ya esta por hablar. Estos 4.5 s hacen que en el caso tipico no suene NADA,
# que es lo correcto — el mejor relleno para una espera corta es el silencio.
DEMORA_RAPIDA = float(os.environ.get("JARVIS_RELLENO_DEMORA_CACHE", "4.5"))

# Cuanto se espera antes del primer relleno. Por debajo de esto no hay espera
# que amenizar y hablar encima seria ruido: los turnos con cache pegado
# arrancan a hablar en 3-4 s.
DEMORA_S = float(os.environ.get("JARVIS_RELLENO_DEMORA", "3.0"))
# Cada cuanto vuelve a decir algo si la cosa sigue. Mas seguido cansa.
CADA_S = float(os.environ.get("JARVIS_RELLENO_CADA", "3.5"))


class Relleno:
    """Habla mientras el modelo piensa, y se calla apenas hay respuesta.

    POR QUE NO ALCANZA EL BIP. `pensando.wav` suena una vez al empezar el turno
    y despues hay 5-40 s de silencio. Un silencio largo despues de un bip no se
    lee como "esta pensando", se lee como "no me oyo" — que es exactamente la
    duda que el bip venia a resolver.

    SE CANCELA, NO SE ESPERA A QUE TERMINE. La cola es FIFO: si un relleno se
    encolara justo cuando llega la primera frase de la respuesta, sonaria
    ANTES que ella y la retrasaria. Por eso el hilo revisa `_corte` inmediato
    antes de encolar, y `cancelar()` lo levanta en cuanto el locutor suelta su
    primera frase.
    """

    def __init__(self, modo: str = "pensando"):
        self.modo = modo if modo in FRASES else "pensando"
        self.rapido = False
        self._corte = threading.Event()
        self._hilo = None

    def poner_rapido(self) -> None:
        """Marca el turno como corto: solo ruidos, y empezando mas tarde.

        Se llama cuando el cache de pensamientos acerta, que es cuando se sabe
        que la respuesta esta por salir. Funciona con el relleno ya corriendo
        porque el lazo relee `self.rapido` en cada vuelta.
        """
        self.rapido = True

    def poner_modo(self, modo: str) -> None:
        """Cambia lo que dice con el relleno YA corriendo.

        Hace falta porque el turno no sabe de entrada que va a hacer: la
        busqueda se decide despues de traducir, y que haya memorias
        recuperadas se sabe recien al armar el tablero. El relleno arranca
        generico y se especializa cuando el turno se define.
        """
        if modo in FRASES:
            self.modo = modo

    def arrancar(self) -> None:
        if self._hilo is not None:
            return
        self._hilo = threading.Thread(target=self._lazo, daemon=True,
                                      name="russ-relleno")
        self._hilo.start()

    def cancelar(self) -> None:
        self._corte.set()

    def _lazo(self) -> None:
        """Recorre RITMO y se queda en el ultimo paso si la espera sigue.

        No vuelve al principio al terminar la lista: quedarse en el ultimo paso
        es lo que produce la escalada. Volver a empezar haria que a los 45 s
        dijera otra vez "Let me think", que es justo lo que suena a bucle roto.
        """
        import random
        dichas = {"ruido": set(), "frase": set()}
        paso = 0
        # Se decide al arrancar el hilo: el cache se consulta antes que esto.
        espera = DEMORA_RAPIDA if self.rapido else DEMORA_S
        while not self._corte.wait(espera):
            ritmo = RITMO_RAPIDO if self.rapido else RITMO
            que = ritmo[min(paso, len(ritmo) - 1)]
            paso += 1
            espera = CADA_S

            if que is None:
                # Ultimo escalon: solo el pitido, sin sintetizar nada.
                if not self._corte.is_set():
                    sonar("pensando")
                continue

            fuente = ONOMATOPEYAS if que == "ruido" else FRASES[self.modo]
            # Sin repetir hasta agotar. La memoria es POR TIPO: gastar todos
            # los ruidos no deberia forzar a repetir frases.
            libres = [x for x in fuente if x not in dichas[que]]
            if not libres:
                dichas[que].clear()
                libres = fuente
            elegida = random.choice(libres)
            dichas[que].add(elegida)

            if self._corte.is_set():
                return       # llego la respuesta mientras elegiamos
            decir(elegida)


class Locutor:
    """Acumula tokens y suelta frases enteras al parlante.

    Existe porque el LLM entrega palabra por palabra y el sintetizador necesita
    unidades con entonacion. Cortar en cada punto es el equilibrio: mas corto
    suena picado, mas largo retrasa el arranque del audio.
    """

    def __init__(self, al_primera=None):
        self._buf = ""
        # Se llama UNA vez, al soltar la primera frase. Es la señal de que la
        # respuesta empezo y hay que callar el relleno.
        self._al_primera = al_primera
        self._arranco = False

    def __call__(self, trozo: str) -> None:
        self._buf += trozo
        while True:
            m = CORTE.search(self._buf)
            if not m:
                return
            frase, resto = self._buf[:m.end()].strip(), self._buf[m.end():]
            if len(frase) < MINIMO and resto:
                return          # muy corta: se junta con la siguiente
            self._buf = resto
            if frase:
                if not self._arranco:
                    self._arranco = True
                    if self._al_primera:
                        self._al_primera()
                decir(frase)

    def cerrar(self) -> None:
        if self._buf.strip():
            if not self._arranco:
                self._arranco = True
                if self._al_primera:
                    self._al_primera()
            decir(self._buf.strip())
        self._buf = ""


# ------------------------------------------------------------------- sonidos

def sonidos() -> list:
    os.makedirs(DIR_SONIDOS, exist_ok=True)
    hay = {f[:-4] for f in os.listdir(DIR_SONIDOS) if f.endswith(".wav")}
    return [{"evento": e, "cuando": d, "tiene": e in hay,
             "kb": round(os.path.getsize(os.path.join(DIR_SONIDOS, e + ".wav")) / 1024, 1)
             if e in hay else 0}
            for e, d in EVENTOS.items()]


def guardar_sonido(evento: str, datos: bytes) -> dict:
    if evento not in EVENTOS:
        return {"ok": False, "motivo": "evento desconocido"}
    os.makedirs(DIR_SONIDOS, exist_ok=True)
    with open(os.path.join(DIR_SONIDOS, evento + ".wav"), "wb") as f:
        f.write(datos)
    return {"ok": True, "evento": evento}


def borrar_sonido(evento: str) -> dict:
    ruta = os.path.join(DIR_SONIDOS, evento + ".wav")
    if os.path.exists(ruta):
        os.unlink(ruta)
    return {"ok": True, "evento": evento}


def parametros() -> dict:
    """Que se puede tocar, en que rango, que significa y como esta ahora.

    Manda el backend y no una copia en el front: los rangos salen de lo que
    acepta piper, y `speaker_id` depende del modelo cargado.
    """
    voz = voz_actual()
    n_hablantes = 1
    defectos = {}
    try:
        v = _cargar()
        n_hablantes = getattr(v.config, "num_speakers", 1) or 1
        for k in ("length_scale", "noise_scale", "noise_w_scale"):
            defectos[k] = getattr(v.config, k, None)
    except Exception:
        pass
    spec = {}
    for k, d in PARAMS.items():
        item = dict(d)
        if k == "speaker_id":
            item["max"] = n_hablantes - 1
        if defectos.get(k) is not None:
            item["defecto"] = defectos[k]
        spec[k] = item
    return {"voz": voz, "hablantes": n_hablantes, "spec": spec,
            "actual": params(voz)}


def estado() -> dict:
    r = robot()
    return dict(_estado, voz=voz_actual(), volumen=volumen(),
                fonemas=idioma_fonemas(),
                activo=runtime.activo("tts"),
                en_cola=_cola.qsize() + _cola_audio.qsize(),
                voces=len(voces()), robot=r["preset"],
                robot_ajustes=r["ajustes"], presets=r["presets"])


# ---------------------------------------------------------------- catalogo

CATALOGO_URL = ("https://huggingface.co/rhasspy/piper-voices/"
                "resolve/main/voices.json")
_catalogo_cache: dict = {}


def catalogo(idioma: str | None = None, buscar: str = "") -> list:
    """Las voces que se pueden bajar. Se cachea en memoria: es un JSON de
    varios cientos de KB y no cambia entre reinicios.

    Todas sirven para español, no solo las `es_*` — se fonemiza aparte. Por eso
    el filtro por idioma es una comodidad para buscar timbres, no una
    restriccion.
    """
    import json as _json
    import urllib.request

    if not _catalogo_cache:
        with urllib.request.urlopen(CATALOGO_URL, timeout=60) as r:
            _catalogo_cache.update(_json.load(r))

    bajadas = {v["nombre"] for v in voces()}
    salida = []
    for clave, v in _catalogo_cache.items():
        if idioma and not clave.startswith(idioma):
            continue
        if buscar and buscar.lower() not in clave.lower():
            continue
        salida.append({
            "nombre": clave,
            "idioma": v.get("language", {}).get("name_native", clave.split("-")[0]),
            "codigo": clave.split("-")[0],
            "calidad": v.get("quality", ""),
            "bajada": clave in bajadas,
        })
    return sorted(salida, key=lambda x: x["nombre"])


def bajar(nombre: str) -> dict:
    """Baja una voz del catalogo. Sincrono a proposito: son 30-110 MB y el
    panel necesita saber cuando termino para poder probarla."""
    import subprocess as sp
    import sys as _sys

    if any(v["nombre"] == nombre for v in voces()):
        return {"ok": True, "ya_estaba": True, "voz": nombre}
    os.makedirs(DIR_VOCES, exist_ok=True)
    r = sp.run([_sys.executable, "-m", "piper.download_voices",
                "--download-dir", DIR_VOCES, nombre],
               capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        return {"ok": False, "motivo": (r.stderr or r.stdout)[-200:]}
    # Una descarga cortada deja un .onnx que pesa casi lo correcto y no abre;
    # se verifica aca y no al usarla, que es cuando duele.
    try:
        from piper import PiperVoice
        PiperVoice.load(os.path.join(DIR_VOCES, nombre + ".onnx"))
    except Exception as e:
        for ext in (".onnx", ".onnx.json"):
            try:
                os.unlink(os.path.join(DIR_VOCES, nombre + ext))
            except OSError:
                pass
        return {"ok": False, "motivo": f"bajada corrupta ({type(e).__name__}), borrada"}
    return {"ok": True, "voz": nombre}


def borrar_voz(nombre: str) -> dict:
    if nombre == voz_actual():
        return {"ok": False, "motivo": "es la voz activa"}
    n = 0
    for ext in (".onnx", ".onnx.json"):
        ruta = os.path.join(DIR_VOCES, nombre + ext)
        if os.path.exists(ruta):
            os.unlink(ruta)
            n += 1
    _rotas.discard(nombre)
    return {"ok": bool(n), "voz": nombre}
