"""Motor remoto: Groq, para cuando lo que importa es que la charla fluya.

Existe porque en esta maquina no hay forma de tener las dos cosas. Medido con
el mismo prompt y la misma charla, a 8 hilos:

    Qwen3-0.6B local   41 tok/s   personaje: no lo sostiene, repite la entrada
    Qwen3-1.7B local   18 tok/s   personaje: recita los ejemplos textuales
    Qwen3-4B   local    8 tok/s   personaje: bien, pero 3-4.5s por turno
    llama-3.3-70b Groq ~275 tok/s

Sin GPU, el modelo local esta limitado por ancho de banda de memoria: o es
rapido y tonto, o es decente y lento. Groq rompe ese compromiso, al precio de
necesitar internet y de que lo que escribis salga de la maquina.

El local sigue siendo el default: es el que va a manejar el robot y el que
funciona con el wifi caido.
"""
import os
import threading
import time

from dotenv import load_dotenv

load_dotenv()

MODELO = os.environ.get("JARVIS_GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOKENS = 220
TEMPERATURA = 0.7

_cliente = None
_lock_carga = threading.Lock()
_lock_gen = threading.Lock()
_estado = {"modelo": MODELO, "motor": "groq", "cargado": False,
           "generando": False, "tok_s": 0.0, "tokens": 0, "ultima_ms": 0,
           "prefill_ms": 0, "error": None}


def cargar():
    global _cliente
    with _lock_carga:
        if _cliente is None:
            from groq import Groq
            clave = os.environ.get("GROQ_API_KEY")
            if not clave:
                raise RuntimeError("falta GROQ_API_KEY en el .env")
            _cliente = Groq(api_key=clave)
            _estado["cargado"] = True
        return _cliente


def descargar():
    global _cliente
    with _lock_carga:
        _cliente = None
        _estado.update(cargado=False, generando=False)
    return estado()


def generar(mensajes: list, al_token=None) -> str:
    cliente = cargar()
    with _lock_gen:
        _estado.update(generando=True, error=None)
        t0 = time.time()
        trozos, t_primero, n = [], None, 0
        try:
            stream = cliente.chat.completions.create(
                model=MODELO, messages=mensajes, stream=True,
                max_tokens=MAX_TOKENS, temperature=TEMPERATURA)
            for ev in stream:
                trozo = ev.choices[0].delta.content
                if not trozo:
                    continue
                if t_primero is None:
                    t_primero = time.time()   # aca la espera es la red, no el prefill
                n += 1
                trozos.append(trozo)
                if al_token:
                    al_token(trozo)
        except Exception as e:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:120]}"

        ahora = time.time()
        dt = max(ahora - (t_primero or t0), 1e-3)
        _estado.update(generando=False, tokens=n, tok_s=round(n / dt, 1),
                       ultima_ms=int((ahora - t0) * 1000),
                       prefill_ms=int(((t_primero or t0) - t0) * 1000))
        return "".join(trozos).strip()


def estado() -> dict:
    return dict(_estado)
