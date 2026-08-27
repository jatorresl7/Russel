"""Presupuesto central de recursos de Jarvis.

Un solo lugar decide: que dispositivo usa cada modulo (CPU o GPU), cuantos
hilos le tocan, y si esta encendido. Antes esto estaba disperso en tres
archivos con numeros a mano, y por eso los modulos se pisaban entre si.

Cuando aparezca una GPU no hay que tocar los servicios: este archivo la
detecta y les cambia el dispositivo solo.
"""
import os
import threading

MODULOS = ("vision", "asr_stream", "asr_final", "vad", "llm", "embed", "iniciativa")

# Peso relativo de cada modulo al repartir los hilos de CPU.
PESOS = {"vision": 6, "asr_stream": 3, "asr_final": 9, "vad": 1, "llm": 4,
         "embed": 2, "iniciativa": 0}

# Que se enciende por defecto. En CPU, tener todo prendido satura la maquina;
# el usuario decide que quiere corriendo.
# asr_stream apagado: partir el audio en vivo (LocalAgreement + vosk) sale
# carisimo en CPU y el texto igual se rehace entero en la pasada final.
# Preferimos esperar a la frase completa y gastar esa CPU en transcribir bien.
# embed prendido: es barato (un MiniLM de 118M) y sin el la memoria no puede
# ni guardar ni recuperar. Se puede apagar, y entonces Russ sigue hablando pero
# sin acordarse de nada.
POR_DEFECTO = {"vision": True, "asr_stream": False, "asr_final": True,
               "vad": True, "llm": False, "embed": True,
               # La unica arista que hace que Russ hable sin que le hablen.
               # Apagada: es la que hay que ajustar viendola fallar.
               "iniciativa": False}

_lock = threading.Lock()
_activos = dict(POR_DEFECTO)
_gpu = None


def hay_gpu() -> bool:
    global _gpu
    if _gpu is None:
        try:
            import torch
            _gpu = bool(torch.cuda.is_available())
        except Exception:
            _gpu = False
    return _gpu


def device() -> str:
    return "cuda" if hay_gpu() else "cpu"


def compute_type() -> str:
    """Tipo de cuantizacion para faster-whisper segun el dispositivo."""
    return "float16" if hay_gpu() else "int8"


def total_hilos() -> int:
    return os.cpu_count() or 4


# Modulos que NUNCA corren a la vez, y por lo tanto no tienen por que
# repartirse los hilos. En el camino de voz el orden es estrictamente
# secuencial: el VAD cierra la frase -> whisper la transcribe -> recien ahi
# arranca el LLM. Mientras el LLM genera, la pasada final de whisper ya
# termino. Repartir entre los dos les daba la mitad de hilos a cada uno para
# un conflicto que no existe: medido, el LLM pasaba de 8 a 3 hilos y de 8.4 a
# ~4 tok/s por nada.
SECUENCIALES = {"llm": ("asr_final", "embed"), "asr_final": ("llm",),
                "embed": ("llm",)}


# Techo por modulo. El reparto por peso reparte de mas: da por hecho que mas
# hilos es mejor, y para llama.cpp en CPU eso es falso pasado cierto punto.
#
# Medido en esta maquina (16 nucleos, Qwen3-4B-Q4_K_M, generacion greedy, con
# vision prendida como corre de verdad):
#
#     1 hilo    4.29 tok/s
#     4 hilos   7.21 tok/s   <- optimo
#     8 hilos   6.14 tok/s
#    16 hilos   0.20 tok/s   <- colapso
#
# Los 16 no son "un poco peor", son treinta veces peor: con vision y whisper
# tambien pidiendo hilos, pedir la maquina entera sobresuscribe los nucleos y
# los workers se pasan el tiempo peleandose el scheduler en vez de generando.
#
# Sin este techo, APAGAR la vision le daba 12 hilos al LLM y lo hundia: la
# accion que parece que deberia acelerarlo lo frenaba.
TECHOS = {"llm": 4}


def hilos(modulo: str) -> int:
    """Hilos que le tocan a un modulo, repartidos entre los que esten activos.

    Con GPU el reparto deja de importar tanto: el trabajo pesado se va a la
    tarjeta y la CPU queda para orquestar.
    """
    if modulo not in PESOS:
        return 1
    techo = TECHOS.get(modulo, total_hilos())
    if hay_gpu():
        return min(techo, max(2, total_hilos() // 4))

    ajenos = SECUENCIALES.get(modulo, ())
    with _lock:
        vivos = {m: PESOS[m] for m in PESOS
                 if _activos.get(m) and m not in ajenos}
    if modulo not in vivos:
        return 1
    suma = sum(vivos.values()) or 1
    porcion = int(total_hilos() * vivos[modulo] / suma)
    return max(1, min(techo, porcion))


def activo(modulo: str) -> bool:
    with _lock:
        return bool(_activos.get(modulo, False))


def activar(modulo: str, on: bool) -> dict:
    with _lock:
        if modulo in _activos:
            _activos[modulo] = bool(on)
    return estado()


def estado() -> dict:
    with _lock:
        activos = dict(_activos)
    return {
        "device": device(),
        "gpu": hay_gpu(),
        "compute_type": compute_type(),
        "total_hilos": total_hilos(),
        "modulos": {m: {"activo": activos.get(m, False), "hilos": hilos(m),
                        "peso": PESOS.get(m, 0)} for m in MODULOS},
    }
