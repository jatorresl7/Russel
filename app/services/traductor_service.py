"""Español -> ingles, local, para lo unico que hace falta: el prompt.

POR QUE EXISTE. Russ contesta en ingles porque ahi es donde suenan bien las
voces de Piper (en español hay nueve en total y ninguna convencio; el catalogo
ingles tiene decenas). Pero Jaime le habla en español, y eso dejaba al modelo
con la ultima linea del prompt en un idioma y todo lo demas en otro. Medido: sin
ninguna instruccion de idioma contestaba español en 2 de 4 turnos, porque el
mensaje del usuario es lo ultimo que lee y pesa mas que el resto.

La alternativa era decirselo en el system —"Spanish in, English out"— y
funcionaba, pero lo RECITABA: a "que estas mirando" contesto "I'm just a robot
listening to you speak in Spanish and responding in English". Cualquier frase
distintiva del prompt termina saliendo por el parlante cuando no tiene nada
mejor que decir. Traduciendo en la entrada el problema desaparece en el origen:
no hay nada que instruir, porque no hay dos idiomas.

SOLO SE TRADUCE LO QUE VA AL PROMPT. El texto español se sigue usando para todo
lo demas, y esto es deliberado:

  - buscar pensamientos: los 292 disparadores estan en español. Medido con la
    entrada traducida, el cache cae de 9/10 a 4/10. Traducir antes de buscar
    costaria mas de la mitad de los aciertos.
  - buscar memorias: se consolidaron de conversaciones en español.
  - historial y consola: se muestra lo que dijiste, no una version de lo que
    dijiste.

POR QUE NO `task="translate"` DE WHISPER, que seria gratis: porque devuelve
ingles Y NADA MAS. Perderiamos el español que necesitan los dos buscadores. El
regalo de latencia no compensa perder el cache.
"""
import threading
import time

from app.core import runtime

import re

MODELO = "Helsinki-NLP/opus-mt-es-en"

# Marcas de que la frase ya viene en ingles. Hace falta porque el modelo es
# es->en y con entrada inglesa NO la deja pasar: la destroza.
#
# Visto en vivo y es el mejor ejemplo de por que esto importa: "tell me a poem"
# salio como "Tell me about it.", asi que Russ recibio «contame de eso» y
# siguio hablando del tema anterior. No alucino nada — contesto exactamente lo
# que le llego. Un bug de traduccion se ve igual que un bug del modelo, y se
# arregla en lados distintos.
_ES = re.compile(r'[ñáéíóúü¿¡]|\b(el|la|los|las|un|una|de|que|con|para|por|'
                 r'como|donde|cuando|quien|cual|esto|eso|muy|mas|pero|porque|'
                 r'esta|estas|soy|eres|tengo|tienes|hola|gracias)\b', re.I)
_EN = re.compile(r'\b(the|is|are|was|were|what|who|where|when|how|why|'
                 r'this|that|these|those|and|but|with|for|from|about|'
                 r'tell|give|make|know|think|have|has|you|your|please)\b', re.I)


def parece_ingles(texto: str) -> bool:
    """Heuristica barata: cuenta marcas de cada idioma.

    Barata a proposito. Un detector de idioma de verdad seria otro modelo
    cargado en RAM y unos milisegundos por turno para decidir algo que en este
    sistema es casi siempre la misma respuesta: Jaime habla español. Contar
    palabras funcion alcanza, y cuando empata gana el español, que es el caso
    normal.
    """
    t = (texto or "").strip()
    if not t:
        return False
    return len(_EN.findall(t)) > len(_ES.findall(t))

_tok = None
_modelo = None
_lock = threading.Lock()
_estado = {"cargado": False, "traducidas": 0, "ms": 0, "error": None}


def disponible() -> bool:
    return runtime.activo("traductor")


def _cargar():
    global _tok, _modelo
    if _modelo is not None:
        return _tok, _modelo
    with _lock:
        if _modelo is None:
            from transformers import MarianMTModel, MarianTokenizer
            _tok = MarianTokenizer.from_pretrained(MODELO)
            _modelo = MarianMTModel.from_pretrained(MODELO)
            _estado["cargado"] = True
    return _tok, _modelo


def traducir(texto: str) -> str:
    """Devuelve el ingles, o el original si algo falla.

    Devolver el original y no lanzar es a proposito: sin traductor Russ contesta
    igual —quiza en español— y eso es infinitamente mejor que un turno perdido.
    """
    texto = (texto or "").strip()
    if not texto or not disponible():
        return texto
    if parece_ingles(texto):
        return texto          # ya esta en el idioma del prompt
    try:
        t0 = time.time()
        tok, modelo = _cargar()
        lote = tok([texto], return_tensors="pt", padding=True, truncation=True,
                   max_length=256)
        salida = modelo.generate(**lote, max_new_tokens=128)
        ingles = tok.decode(salida[0], skip_special_tokens=True).strip()
        _estado.update(traducidas=_estado["traducidas"] + 1,
                       ms=int((time.time() - t0) * 1000), error=None)
        return ingles or texto
    except Exception as e:
        _estado["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        return texto


def precargar() -> None:
    """Trae el modelo a RAM fuera de un turno.

    Importa MUCHO que sea fuera: la primera carga tarda ~60 s bajando pesos, y
    ademas importa `transformers`. Hacerlo dentro de un turno mientras el
    detector de vision importa `torchvision` fue exactamente el deadlock de
    locks de importacion que colgo el server entero. Ver
    `vision_service.abrir_al_arrancar`.
    """
    if not disponible():
        return
    try:
        _cargar()
    except Exception as e:
        _estado["error"] = f"{type(e).__name__}: {str(e)[:80]}"


def estado() -> dict:
    return dict(_estado, activo=disponible(), modelo=MODELO)
