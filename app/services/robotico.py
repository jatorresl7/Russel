"""Convertir la voz de Piper en una voz de robot.

POR QUE HACE FALTA. Piper esta entrenado para sonar humano — es literalmente su
objetivo — asi que ninguna de sus voces suena a robot por mucho que se busque.
Lo que se puede es procesar su salida: la sintesis aporta la inteligibilidad y
los efectos aportan el timbre. Al reves —espeak-ng, que si es robotico de
fabrica— se entiende bastante peor, y una frase que hay que repetir dos veces
deja de ser rapida.

LOS CUATRO EFECTOS, y por que estos.

1. MODULACION EN ANILLO. Es el sonido "robot" por antonomasia: el de los Daleks
   y el de medio cine de ciencia ficcion. Multiplica la onda por una sinusoide
   de 20-80 Hz, lo que parte cada armonico en dos bandas laterales y destruye la
   sensacion de cuerdas vocales. Es el efecto que mas hace y el primero a mover.

2. BITCRUSH. Cuantizar a pocos bits mete ruido de cuantizacion correlacionado
   con la señal, que es exactamente como suena algo digital y barato. Aporta el
   "de juguete" de BMO.

3. SATURACION. Una tangente hiperbolica suave. Agrega armonicos y comprime la
   dinamica, asi que la voz suena pareja y sin respiracion — nadie que respire
   habla con esta envolvente.

4. ECO CORTO. 15-40 ms. Demasiado corto para oirse como eco: se percibe como
   caja metalica. Es lo que da la impresion de que la voz sale de adentro de
   algo.

EL ORDEN NO ES ARBITRARIO. El anillo va primero, sobre la señal limpia, porque
si entra despues de la saturacion modula tambien los armonicos agregados y sale
barro. El eco va ultimo porque es un efecto de espacio: si se satura despues del
eco, se saturan las repeticiones y suena a error.
"""
import numpy as np
from scipy import signal as _sig


# -------------------------------------------------------------- vocoder

def _envolvente(logmag: np.ndarray, corte: int = 30) -> np.ndarray:
    """La envolvente espectral por cepstrum: los coeficientes bajos.

    Es la parte del espectro que lleva los FORMANTES, o sea las palabras. Lo
    que queda afuera son los armonicos, o sea el tono de quien habla. Separar
    las dos cosas es lo que permite quedarse con el contenido y tirar la voz.
    """
    cep = np.fft.irfft(logmag, axis=0)
    cep[corte:-corte] = 0
    n = logmag.shape[0] * 2 - 2
    return np.fft.rfft(cep, n=n, axis=0)[:logmag.shape[0]].real


def _portador(n: int, sr: int, f0: float) -> np.ndarray:
    """El zumbido sobre el que se moldea la voz. Limitado en banda, sumando
    senos uno por uno.

    NO SE PUEDE USAR `scipy.signal.sawtooth` ACA, y esta medido: genera la
    rampa cruda, sin limitar, asi que sus armonicos pasan Nyquist y vuelven
    DOBLADOS como frecuencias que no son multiplo de f0. A 110 Hz con muestreo
    de 22 kHz eso era el 33.7% de la energia del portador — un tercio del
    zumbido era ruido inarmonico. Sumando senos hasta Nyquist da 0.0%, y esa
    es toda la diferencia entre un robot limpio y uno que raspa.

    El `1/k**0.8` es la caida de los armonicos. Plano seria mas brillante pero
    chilla; 1/k (la caida natural de una rampa) apaga demasiado y la voz pierde
    consonantes. 0.8 esta en el medio.
    """
    t = np.arange(n, dtype=np.float32) / sr
    y = np.zeros(n, dtype=np.float32)
    tope = sr / 2 * 0.95
    k = 1
    while k * f0 < tope:
        y += np.sin(2 * np.pi * k * f0 * t, dtype=np.float32) / (k ** 0.8)
        k += 1
    pico = float(np.max(np.abs(y))) or 1.0
    return (y / pico).astype(np.float32)


def _vocoder(x: np.ndarray, sr: int, f0: float, mezcla: float,
             tilt: float = 2.0) -> np.ndarray:
    """El robot de verdad: la voz pierde su tono y conserva sus palabras.

    POR QUE ESTE Y NO EL TONO. Mover el tono y los formantes cambia el TAMAÑO
    de quien habla — sale una persona mas chica o mas grande, pero una persona.
    Lo que se lee como maquina son otras dos cosas: que la entonacion sea plana
    y que el timbre no venga de una garganta. El vocoder da las dos juntas.

    COMO. Se le saca al habla la envolvente espectral, que es donde viven los
    formantes y por lo tanto la inteligibilidad, y se la aplica a un zumbido
    sintetico de frecuencia FIJA. El resultado articula exactamente lo mismo
    —cada consonante y cada vocal siguen ahi— pero sobre un tono constante que
    ninguna persona podria sostener. Por eso se entiende todo y sin embargo es
    obvio que no habla nadie.

    `f0` es la altura del zumbido: 90-110 Hz suena a robot grande y serio,
    150-200 Hz a robot chico. `mezcla` deja pasar algo de la voz original, que
    ayuda con las consonantes sordas —la ese y la efe no tienen tono, asi que
    el zumbido no las representa bien— a cambio de sonar menos maquina.
    """
    if mezcla <= 0 or f0 <= 0:
        return x
    n_fft, hop = 1024, 256
    _, _, Z = _sig.stft(x, nperseg=n_fft, noverlap=n_fft - hop)
    logmag = np.log(np.abs(Z) + 1e-9)
    env = _envolvente(logmag)

    portador = _portador(len(x), sr, f0)
    _, _, P = _sig.stft(portador, nperseg=n_fft, noverlap=n_fft - hop)
    P = P[:, :Z.shape[1]]
    if P.shape[1] < Z.shape[1]:
        P = np.pad(P, ((0, 0), (0, Z.shape[1] - P.shape[1])))

    # Se aplana el portador antes de moldearlo: su propia envolvente (la caida
    # natural del diente de sierra) se sumaria a la de la voz y embarraria los
    # formantes.
    p_log = np.log(np.abs(P) + 1e-9)
    p_plano = p_log - _envolvente(p_log)

    # INCLINACION GLOTAL, y esto es lo que separa un robot de un zumbido.
    #
    # Arriba se aplana el portador restandole su envolvente, para que no
    # ensucie los formantes. Pero eso deja una excitacion de espectro PLANO, y
    # ninguna fuente sonora real es plana: la glotis humana cae unos 12 dB por
    # octava. Sin esta inclinacion el resultado tiene ~12% de energia arriba de
    # 4 kHz contra 8% de la voz original, y ese exceso de agudos es exactamente
    # lo que se oye como aspero.
    #
    # Se aplica DESPUES de aplanar y ANTES de la envolvente de la voz: es una
    # propiedad de la fuente, no del tracto.
    #
    # EL VALOR ES 2, NO 12, y salio de medir en vez de razonar. La glotis
    # humana cae ~12 dB/octava y ese fue el primer intento; con 12 la voz sale
    # apagada (centroide 1106 Hz contra 1335 de la original). La razon es que
    # la envolvente cepstral de la voz YA arrastra buena parte de esa
    # inclinacion, asi que aplicarla entera la cuenta dos veces. Barriendo de 1
    # a 6 contra el brillo de la voz limpia, 2 dB/octava da 4.9% de energia
    # sobre 4 kHz contra 5.1% del original: practicamente identico.
    if tilt:
        frec = np.fft.rfftfreq(n_fft, 1 / sr)
        frec[0] = frec[1]
        octavas = np.log2(frec / max(f0, 1.0))
        # de dB a logaritmo natural: 8.686 dB por neper
        p_plano = p_plano - (tilt / 8.686) * octavas[:, None]

    Z2 = np.exp(p_plano + env) * np.exp(1j * np.angle(P))
    _, y = _sig.istft(Z2, nperseg=n_fft, noverlap=n_fft - hop)
    y = (y[:len(x)] if len(y) >= len(x)
         else np.pad(y, (0, len(x) - len(y)))).astype(np.float32)

    pico = float(np.max(np.abs(y))) or 1.0
    y = y / pico * (float(np.max(np.abs(x))) or 1.0)
    return x * (1 - mezcla) + y * mezcla


# ---------------------------------------------------------------- tono

def semitonos_a_factor(st: float) -> float:
    """Semitonos -> razon de remuestreo. 12 semitonos = una octava = x2.

    La interfaz habla en semitonos y no en razones porque una razon no se
    intuye: nadie sabe si 1.18 es mucho o poco, y +3 semitonos si. Es ademas
    como lo expresan todas las herramientas del rubro.
    """
    return float(2.0 ** (st / 12.0))


def _tono(x: np.ndarray, factor: float) -> np.ndarray:
    """Cambia el tono remuestreando. Sube el tono Y acelera, las dos cosas.

    Se hace asi y no con un phase vocoder —que preservaria la duracion— por dos
    motivos. Uno: el vocoder introduce el tipico artefacto metalico de fase en
    las consonantes, y aca la inteligibilidad es lo que estamos cuidando. Dos:
    que acelere es un REGALO, no un defecto. Todo el dia venimos peleando la
    latencia; subir el tono un 15% acorta el audio un 15%.

    Y si la velocidad molesta, se compensa gratis desde el otro lado:
    `length_scale` de Piper alarga la sintesis antes de que llegue aca.
    """
    if abs(factor - 1.0) < 0.01:
        return x
    n = max(1, int(round(len(x) / factor)))
    return _sig.resample(x, n).astype(np.float32)


def _formante(x: np.ndarray, sr: int, factor: float) -> np.ndarray:
    """Mueve los formantes SIN mover el tono. Esto es lo que hace el robot.

    ESTE ES EL EFECTO QUE FALTABA. Subir el tono a secas da ardilla, porque los
    formantes —las resonancias del tracto vocal, que son lo que dice el TAMAÑO
    de quien habla— suben con el. Un robot chico y simpatico es tono arriba con
    formantes ABAJO: la voz suena aguda pero el cuerpo que la produce no suena
    encogido. Esa es la diferencia entre BMO y un chipmunk, y es la unica razon
    por la que el anillo y el bitcrush sonaban a basura: atacaban el timbre por
    donde no era.

    COMO. En cada trama se separa la envolvente espectral (que lleva los
    formantes) de la estructura fina (que lleva los armonicos, o sea el tono).
    La separacion es por cepstrum: la envolvente son los coeficientes bajos.
    Se deforma SOLO la envolvente en el eje de frecuencia y se vuelve a sumar
    la estructura fina intacta. Por eso el tono no se entera.
    """
    if abs(factor - 1.0) < 0.01:
        return x
    n_fft, hop = 1024, 256
    f, t, Z = _sig.stft(x, nperseg=n_fft, noverlap=n_fft - hop)
    mag, fase = np.abs(Z), np.angle(Z)
    logmag = np.log(mag + 1e-9)

    # Cepstrum: los primeros coeficientes son la envolvente, el resto los
    # armonicos. 30 es el corte habitual para voz a esta resolucion.
    cep = np.fft.irfft(logmag, axis=0)
    corte = 30
    cep_env = cep.copy()
    cep_env[corte:-corte] = 0
    env = np.fft.rfft(cep_env, n=logmag.shape[0] * 2 - 2, axis=0)[:logmag.shape[0]].real
    fino = logmag - env

    bins = np.arange(env.shape[0])
    origen = bins / factor
    env2 = np.empty_like(env)
    for i in range(env.shape[1]):
        env2[:, i] = np.interp(origen, bins, env[:, i])

    Z2 = np.exp(env2 + fino) * np.exp(1j * fase)
    _, y = _sig.istft(Z2, nperseg=n_fft, noverlap=n_fft - hop)
    return y[:len(x)].astype(np.float32) if len(y) >= len(x) else \
        np.pad(y, (0, len(x) - len(y))).astype(np.float32)


# Los presets. Nacen de escuchar, no de una teoria — cada uno apunta a un robot
# distinto y a proposito ninguno lleva el anillo al maximo: pasado ~0.6 de mezcla
# la voz deja de entenderse, y un robot que no se entiende no sirve de nada.
# RANGOS SEGUROS, y esto importa mas que los presets.
#
# La primera version dejaba el tono entre 0.7 y 1.5 y el formante entre 0.7 y
# 1.4. Con esos limites casi cualquier movimiento sonaba mal, porque lo util
# esta en una franja mucho mas angosta y el resto del recorrido es basura. Un
# slider donde el 80% del recorrido suena horrible no es configurable: es una
# trampa. Ahora los limites SON la franja util, asi que cualquier posicion es
# defendible.
LIMITES = {
    "voc_mix":   (0.0, 1.0),     # 1.0 = solo zumbido; 0.7-0.9 es lo usable
    "voc_hz":    (60, 260),
    "voc_tilt":  (0.0, 8.0),     # dB/octava. 0 = plano y aspero; 2 = natural
    "semitonos": (-5.0, 5.0),    # mas de una cuarta y deja de ser la misma voz
    "formante":  (0.86, 1.16),   # bajo 0.85 se adelgaza y se come consonantes
    "drive":     (0.0, 0.35),    # arriba de eso empasta las vocales
    "eco_mix":   (0.0, 0.35),
    "eco_ms":    (0, 45),
    "anillo_mix": (0.0, 0.7),
    "anillo_hz": (0, 120),
    "bits":      (0, 12),
}

PRESETS = {
    "ninguno": {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": 0.0, "formante": 1.0, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.0,
                "eco_ms": 0, "eco_mix": 0.0},

    # --- LOS ROBOTICOS DE VERDAD: vocoder ------------------------------------
    # Son los unicos que suenan a MAQUINA. El tono y el formante, solos, dan
    # una persona de otro tamaño — cambian quien habla, no que clase de cosa
    # habla. El vocoder le saca el tono variable, que es la firma de que hay
    # una garganta, y deja las palabras intactas.
    #
    # `voc_mix` no llega a 1.0 a proposito: las consonantes sordas —ese, efe,
    # jota— no tienen tono, asi que el zumbido no las representa y se pierden.
    # Dejar pasar 10-20% de la voz original las recupera y casi no se nota.
    "robot":   {"voc_tilt": 2.0, "voc_hz": 110, "voc_mix": 0.82, "semitonos": 0.0,
                "formante": 1.0, "anillo_hz": 0, "anillo_mix": 0.0, "bits": 0,
                "drive": 0.0, "eco_ms": 0, "eco_mix": 0.0},
    # Robot chico: mismo mecanismo, zumbido mas agudo y cuerpo mas chico.
    "droide":  {"voc_tilt": 2.0, "voc_hz": 175, "voc_mix": 0.80, "semitonos": 0.0,
                "formante": 0.94, "anillo_hz": 0, "anillo_mix": 0.0, "bits": 0,
                "drive": 0.0, "eco_ms": 0, "eco_mix": 0.0},
    # Robot grande y serio. Zumbido grave y caja.
    "maquina": {"voc_tilt": 2.0, "voc_hz": 88, "voc_mix": 0.85, "semitonos": 0.0,
                "formante": 1.06, "anillo_hz": 0, "anillo_mix": 0.0, "bits": 0,
                "drive": 0.0, "eco_ms": 22, "eco_mix": 0.14},
    # A medias: se nota que es raro pero conserva bastante de la voz.
    "medio":   {"voc_tilt": 2.0, "voc_hz": 130, "voc_mix": 0.50, "semitonos": 1.0,
                "formante": 0.97, "anillo_hz": 0, "anillo_mix": 0.0, "bits": 0,
                "drive": 0.0, "eco_ms": 0, "eco_mix": 0.0},

    # --- tono y formante limpios: otra persona, no otra cosa -----------------
    # Apenas se nota que no es una persona. El mas seguro.
    "suave":   {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": 1.0, "formante": 0.95, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.05,
                "eco_ms": 10, "eco_mix": 0.08},
    # Robot chico y simpatico: agudo, pero con el cuerpo mas chico todavia.
    "bmo":     {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": 2.5, "formante": 0.90, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.08,
                "eco_ms": 14, "eco_mix": 0.14},
    "chico":   {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": 4.0, "formante": 0.87, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.10,
                "eco_ms": 12, "eco_mix": 0.12},
    # Grave y con caja.
    "wall_e":  {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": -1.8, "formante": 1.10, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.15,
                "eco_ms": 30, "eco_mix": 0.24},
    "grande":  {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": -3.5, "formante": 1.15, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 0, "drive": 0.20,
                "eco_ms": 38, "eco_mix": 0.30},

    # --- los agresivos: quedan, pero no son el camino ------------------------
    # La modulacion en anillo es el efecto Dalek. Sobre voz hablada enturbia las
    # vocales: suena ROTO, no robotico. Se probaron como default y hubo que
    # sacarlos.
    "dalek":   {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": -1.0, "formante": 1.05, "anillo_hz": 30,
                "anillo_mix": 0.55, "bits": 0, "drive": 0.35,
                "eco_ms": 22, "eco_mix": 0.25},
    "radio":   {"voc_tilt": 2.0, "voc_hz": 0, "voc_mix": 0.0, "semitonos": 0.0, "formante": 1.0, "anillo_hz": 0,
                "anillo_mix": 0.0, "bits": 6, "drive": 0.35,
                "eco_ms": 8, "eco_mix": 0.15},
}

# `bmo` y no `wall_e`: el que suena a robot simpatico y se entiende entero.
# El que suena a maquina y se entiende entero.
POR_DEFECTO = "robot"


def _anillo(x: np.ndarray, sr: int, hz: float, mix: float) -> np.ndarray:
    if hz <= 0 or mix <= 0:
        return x
    t = np.arange(len(x), dtype=np.float32) / sr
    return x * (1 - mix) + (x * np.sin(2 * np.pi * hz * t)) * mix


def _bitcrush(x: np.ndarray, bits: int) -> np.ndarray:
    """0 = sin efecto. Por debajo de 5 bits deja de ser voz y pasa a ser ruido,
    asi que ese es el piso util."""
    if not bits or bits >= 16:
        return x
    niveles = 2 ** max(4, bits)
    return np.round(x * niveles) / niveles


def _drive(x: np.ndarray, cantidad: float) -> np.ndarray:
    if cantidad <= 0:
        return x
    g = 1 + cantidad * 9
    return np.tanh(x * g) / np.tanh(g)


def _eco(x: np.ndarray, sr: int, ms: float, mix: float) -> np.ndarray:
    if ms <= 0 or mix <= 0:
        return x
    n = int(sr * ms / 1000)
    if n <= 0 or n >= len(x):
        return x
    retrasado = np.concatenate([np.zeros(n, dtype=np.float32), x[:-n]])
    return x + retrasado * mix


def aplicar(muestras: np.ndarray, sr: int, cfg: dict) -> np.ndarray:
    """La cadena entera. `muestras` en float32 de -1 a 1.

    EL ORDEN. Primero el tono, que al remuestrear sube tambien los formantes;
    despues la correccion de formantes, que es la que decide el tamaño del
    cuerpo. Los dos van sobre señal limpia: cualquier distorsion antes les
    mete armonicos que despues se deforman y salen como metal sucio.

    Los agresivos van al final y en este orden: el anillo sobre lo ya afinado,
    el bitcrush y la saturacion despues, y el eco ultimo porque es espacio —
    saturar las repeticiones suena a error.
    """
    x = muestras.astype(np.float32)
    x = _tono(x, semitonos_a_factor(float(cfg.get("semitonos", 0.0) or 0.0)))
    x = _formante(x, sr, float(cfg.get("formante", 1.0) or 1.0))
    x = _vocoder(x, sr, float(cfg.get("voc_hz", 0) or 0),
                 float(cfg.get("voc_mix", 0.0) or 0.0),
                 float(cfg.get("voc_tilt", 2.0)))
    x = _anillo(x, sr, cfg.get("anillo_hz", 0), cfg.get("anillo_mix", 0.0))
    x = _bitcrush(x, int(cfg.get("bits", 0) or 0))
    x = _drive(x, cfg.get("drive", 0.0))
    x = _eco(x, sr, cfg.get("eco_ms", 0), cfg.get("eco_mix", 0.0))

    # Normalizar al final y no antes. La saturacion y el eco suben el pico, y
    # sin esto una frase larga recorta y suena rota justo en las vocales
    # fuertes, que es donde mas se nota.
    pico = float(np.max(np.abs(x))) if len(x) else 0.0
    if pico > 0:
        x = x / pico * 0.92
    return x


def config(preset: str | None, ajustes: dict | None = None) -> dict:
    """Un preset, opcionalmente retocado y siempre dentro de LIMITES.

    El recorte no es paranoia: un valor fuera de rango no da un efecto raro,
    da un efecto roto, y quien lo mando por API no tiene por que saberlo.
    """
    base = dict(PRESETS.get(preset or POR_DEFECTO, PRESETS[POR_DEFECTO]))
    if ajustes:
        base.update({k: v for k, v in ajustes.items() if k in base})
    for k, (lo, hi) in LIMITES.items():
        if k in base and base[k] is not None:
            base[k] = max(lo, min(hi, type(lo)(base[k])))
    return base
