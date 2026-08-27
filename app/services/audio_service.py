"""Transcripcion en vivo, 100% local, siguiendo los metodos publicados.

  VAD        : Silero v5 por ONNX puro (sin torch, que aca es build CUDA sin GPU).
               Endpointing por silencio >600ms, como recomienda la literatura.
  Streaming  : politica LocalAgreement-2 de Machacek, Dabre y Bojar (2023),
               "Turning Whisper into Real-Time Transcription System",
               arXiv:2307.14743 -- github.com/ufal/whisper_streaming

LocalAgreement-2: en vez de cortar el audio a ciegas y esperar, corremos
Whisper repetidamente sobre un buffer que crece y damos por CONFIRMADAS solo
las palabras en las que dos pasadas consecutivas coinciden desde el principio.
Lo confirmado se fija y su audio se descarta; el resto queda abierto. Asi el
texto nunca "baila" y nunca se parte una palabra por la mitad.

Hilos, a proposito separados:
  lector      -> solo lee arecord y encola. Nunca hace trabajo pesado.
  procesador  -> VAD + LocalAgreement.
"""
import collections
import json
import os
import queue
import subprocess
import threading
import time

import numpy as np

from app.core import runtime
from app.services import assistant_service

RATE = 16000
FRAME_MS = 32
FRAME_SAMPLES = 512                    # Silero v5: 512 muestras nuevas por paso
CONTEXTO = 64                          # ...mas 64 del paso anterior. Sin este
                                       # contexto el modelo devuelve ~0 siempre.
FRAME_BYTES = FRAME_SAMPLES * 2

# Renunciamos a transcribir en vivo y esperamos la frase entera. A cambio,
# toda la CPU va a esta unica pasada, que es la que produce el texto real.
WHISPER_MODEL = "large-v3-turbo"
STREAM_MODEL = "base"                  # pasadas en vivo: tienen que ir rapido
SILERO_ONNX = os.path.expanduser("~/.cache/silero/silero_vad.onnx")

VAD_UMBRAL = 0.5                       # prob de voz para considerar habla
SILENCIO_FIN = 0.6                     # 600ms de silencio cierra la frase
PROCESA_CADA = 0.8                     # cada cuanto corre una pasada de whisper
VOSK_DIR = os.path.expanduser("~/.cache/vosk/vosk-model-small-es-0.42")
BUFFER_MAX = 11.0                      # frases mas cortas -> la pasada final
                                       # nunca monopoliza la CPU 10s seguidos
PULIR_CON_TURBO = True                 # False = usar solo el texto de
                                       # LocalAgreement (como el paper) y
                                       # eliminar del todo los picos de CPU
BEAM = 1                               # las pasadas de streaming van greedy
BEAM_FINAL = 1                         # medido: beam=5 tarda 1.28x mas y no
                                       # transcribe mejor (en la muestra de
                                       # prueba, peor: "no se" por "nos")
NO_SPEECH_MAX = 0.6                    # descarta segmentos que "no suenan a voz"
LOGPROB_MIN = -1.0                     # descarta segmentos con baja confianza

# Whisper fue entrenado con audio de YouTube y, cuando el audio es ambiguo,
# rellena con muletillas de video. Son alucinaciones conocidas, no transcripcion.
ALUCINACIONES = (
    "gracias por ver", "nos vemos en el proximo", "nos vemos en el próximo",
    "suscribete", "suscríbete", "subtitulos realizados", "subtítulos realizados",
    "amara.org", "no olvides suscribirte", "hasta la proxima", "hasta la próxima",
)


def _es_alucinacion(texto: str) -> bool:
    t = texto.strip().lower()
    return any(f in t for f in ALUCINACIONES)

_whisper = None
_stream_whisper = None
_silero = None
_vosk = None
_running = False
_lock = threading.Lock()
_hilos = []

_frames = queue.Queue(maxsize=1200)
_buf_lock = threading.Lock()
_buf = np.zeros(0, dtype=np.float32)      # audio sin confirmar (LocalAgreement)
_utter = np.zeros(0, dtype=np.float32)    # frase completa (pasada final)
_cerrar = threading.Event()
_la = None
_transcripts = collections.deque(maxlen=40)
# `cargando` y `transcribiendo` existen para la UI y para nada mas. Son los dos
# momentos en que el audio tarda SEGUNDOS y hasta ahora no se veian: cargar los
# modelos al prender el microfono, y la pasada final de whisper al cerrar una
# frase. Sin esto la pantalla se queda igual mientras la maquina esta al maximo,
# y desde afuera es indistinguible de que el microfono no ande.
_estado = {"listening": False, "speaking": False, "vad": 0.0,
           "committed": "", "pending": "", "vosk": "", "dropped": 0, "pasadas": 0,
           "ultima_pasada_ms": 0, "buffer_s": 0.0,
           "cargando": False, "transcribiendo": False,
           "model": WHISPER_MODEL, "loaded": False, "error": None}


def get_stream_whisper():
    global _stream_whisper
    if _stream_whisper is None:
        from faster_whisper import WhisperModel
        _stream_whisper = WhisperModel(STREAM_MODEL, device=runtime.device(),
                                       compute_type=runtime.compute_type(),
                                       cpu_threads=runtime.hilos("asr_stream"))
    return _stream_whisper


def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(WHISPER_MODEL, device=runtime.device(),
                                compute_type=runtime.compute_type(),
                                cpu_threads=runtime.hilos("asr_final"))
        _estado["loaded"] = True
    return _whisper


def get_vosk():
    """Capa instantanea: emite palabras al momento, sin esperar a whisper."""
    global _vosk
    if _vosk is None and os.path.isdir(VOSK_DIR):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        _vosk = KaldiRecognizer(Model(VOSK_DIR), RATE)
    return _vosk


def get_silero():
    global _silero
    if _silero is None:
        import onnxruntime as ort
        if not os.path.isfile(SILERO_ONNX):
            raise RuntimeError(f"falta el modelo silero en {SILERO_ONNX}")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        _silero = ort.InferenceSession(SILERO_ONNX, sess_options=opts,
                                       providers=["CPUExecutionProvider"])
    return _silero


class LocalAgreement:
    """Confirma solo el prefijo comun entre la hipotesis anterior y la nueva."""

    def __init__(self):
        self.previa = []      # hipotesis anterior sobre la zona sin confirmar
        self.confirmadas = []  # palabras ya fijadas

    @staticmethod
    def _igual(a, b):
        return a["w"].strip().lower() == b["w"].strip().lower()

    def insertar(self, nuevas: list) -> list:
        commit, i = [], 0
        while i < len(self.previa) and i < len(nuevas) and self._igual(self.previa[i], nuevas[i]):
            commit.append(nuevas[i])
            i += 1
        self.previa = nuevas[i:]
        self.confirmadas.extend(commit)
        return commit

    def texto_confirmado(self) -> str:
        return "".join(w["w"] for w in self.confirmadas).strip()

    def texto_pendiente(self) -> str:
        return "".join(w["w"] for w in self.previa).strip()

    def reset(self):
        self.previa, self.confirmadas = [], []


def _lector():
    proc = subprocess.Popen(
        ["arecord", "-D", "default", "-f", "S16_LE", "-r", str(RATE),
         "-c", "1", "-t", "raw", "-q"], stdout=subprocess.PIPE)
    _estado["listening"] = True
    try:
        while _running:
            frame = proc.stdout.read(FRAME_BYTES)
            if not frame or len(frame) < FRAME_BYTES:
                break
            try:
                _frames.put_nowait(frame)
            except queue.Full:
                _estado["dropped"] += 1
    finally:
        proc.terminate()
        _estado["listening"] = False


def _pasada(audio: np.ndarray, beam: int, rapido: bool = False,
            con_tiempos: bool = False) -> tuple[str, list]:
    """Devuelve (texto, palabras). Los word_timestamps solo los pide quien
    los necesita: obligan a un alineamiento extra por DTW sobre la atencion
    y la pasada final no los usaba para nada, solo repegaba s.text palabra
    por palabra."""
    modelo = get_stream_whisper() if rapido else get_whisper()
    segs, _ = modelo.transcribe(
        audio, language="es", beam_size=beam, word_timestamps=con_tiempos,
        condition_on_previous_text=False)   # evita que alucine continuando lo anterior
    trozos, palabras = [], []
    for s in segs:
        if getattr(s, "no_speech_prob", 0.0) > NO_SPEECH_MAX:
            continue
        if getattr(s, "avg_logprob", 0.0) < LOGPROB_MIN:
            continue
        if _es_alucinacion(s.text):
            continue
        trozos.append(s.text)
        for w in (s.words or []):
            palabras.append({"w": w.word, "ini": w.start, "fin": w.end})
    return "".join(trozos).strip(), palabras


def _procesador():
    """Solo VAD y acumulacion. Whisper corre en otro hilo a proposito: una
    pasada tarda segundos y si bloqueara este bucle se perderia audio."""
    global _buf, _utter
    sesion = get_silero()
    sr = np.array(RATE, dtype=np.int64)
    estado_vad = np.zeros((2, 1, 128), dtype=np.float32)
    contexto = np.zeros(CONTEXTO, dtype=np.float32)
    rec = get_vosk() if runtime.activo("asr_stream") else None
    silencio = 0.0
    hubo_voz = False

    try:
        while _running:
            try:
                frame = _frames.get(timeout=0.5)
            except queue.Empty:
                continue

            muestras = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
            entrada = np.concatenate([contexto, muestras]).reshape(1, -1)
            out, estado_vad = sesion.run(
                None, {"input": entrada, "state": estado_vad, "sr": sr})
            contexto = muestras[-CONTEXTO:]

            prob = float(out[0][0])
            _estado["vad"] = round(prob, 3)

            if rec is not None and runtime.activo("asr_stream"):
                if rec.AcceptWaveform(frame):
                    _estado["vosk"] = json.loads(rec.Result()).get("text", "").strip()
                else:
                    _estado["vosk"] = json.loads(rec.PartialResult()).get("partial", "").strip()
            hay_voz = prob >= VAD_UMBRAL
            _estado["speaking"] = hay_voz

            if hay_voz:
                silencio = 0.0
                hubo_voz = True
            else:
                silencio += FRAME_SAMPLES / RATE

            if not hubo_voz:
                continue

            with _buf_lock:
                _buf = np.concatenate([_buf, muestras])
                _utter = np.concatenate([_utter, muestras])
                _estado["buffer_s"] = round(len(_utter) / RATE, 1)
                largo = len(_utter) / RATE

            if silencio >= SILENCIO_FIN or largo >= BUFFER_MAX:
                _cerrar.set()
                hubo_voz = False
                silencio = 0.0
    except Exception as e:
        _estado["error"] = f"{type(e).__name__}: {str(e)[:120]}"


def _transcriptor():
    """Pasadas de LocalAgreement en vivo + pasada final precisa al cerrar."""
    global _buf, _utter, _la
    _la = LocalAgreement()
    ultima = 0.0
    while _running:
        time.sleep(0.15)

        if _cerrar.is_set():
            _cerrar.clear()
            with _buf_lock:
                audio, _buf, _utter = _utter.copy(), np.zeros(0, np.float32), np.zeros(0, np.float32)
            if len(audio) / RATE >= 0.6:
                t = time.time()
                _estado["transcribiendo"] = True
                try:
                    texto, _ = _pasada(audio, BEAM_FINAL)  # turbo, preciso
                finally:
                    # En finally: si la pasada revienta, la bandera NO puede
                    # quedarse encendida para siempre diciendo que analiza.
                    _estado["transcribiendo"] = False
                if texto:
                    _transcripts.append({
                        "text": texto, "at": time.strftime("%H:%M:%S"),
                        "dur": round(len(audio) / RATE, 1),
                        "took": round(time.time() - t, 1)})
                    # La frase cerrada va al slot y este hilo sigue de largo.
                    # Si Russ todavia esta contestando la frase anterior, esta
                    # la pisa: cuando termine va a atender la ultima, no a
                    # contestar en fila cosas que ya pasaron.
                    if runtime.activo("llm"):
                        assistant_service.encolar(texto, origen="voz")
            _la.reset()
            _estado.update(committed="", pending="", vosk="", buffer_s=0.0)
            continue

        with _buf_lock:
            audio = _buf.copy()
        if not runtime.activo("asr_stream"):
            continue
        if len(audio) < RATE * 0.6 or time.time() - ultima < PROCESA_CADA:
            continue
        ultima = time.time()

        t = time.time()
        _, palabras = _pasada(audio, BEAM, rapido=True, con_tiempos=True)
        _estado["ultima_pasada_ms"] = int((time.time() - t) * 1000)
        _estado["pasadas"] += 1

        commit = _la.insertar(palabras)
        _estado["committed"] = _la.texto_confirmado()
        _estado["pending"] = _la.texto_pendiente()
        if commit:
            corte = int(commit[-1]["fin"] * RATE)
            with _buf_lock:
                if 0 < corte < len(_buf):
                    _buf = _buf[corte:]


def start() -> dict:
    global _running, _hilos
    with _lock:
        if _running:
            return status()
        _estado["cargando"] = True
        try:
            get_silero()
            get_whisper()
            if runtime.activo("asr_stream"):
                get_vosk()
                get_stream_whisper()
        finally:
            _estado["cargando"] = False
        _running = True
        _hilos = [threading.Thread(target=f, daemon=True)
                  for f in (_lector, _procesador, _transcriptor)]
        for h in _hilos:
            h.start()
    return status()


def stop() -> dict:
    global _running
    _running = False
    _estado.update(listening=False, speaking=False, committed="", pending="", vosk="")
    return status()


def status() -> dict:
    return dict(_estado, transcripts=list(_transcripts)[-12:][::-1])


def clear() -> dict:
    _transcripts.clear()
    return status()
