"""Buscar en la web, automatico, sin que el modelo lo decida.

POR QUE NO ES UNA TOOL. Las tools se sacaron de este proyecto por medicion: el
catalogo ocupaba lugar en el prefijo cacheado, la gramatica GBNF restringia el
sampling en CADA turno, y con todo eso Qwen3-4B elegia mal cuando llamar. La
regla que quedo fue «por RAG en automatico, asi siempre hace caso y es rapido».
Esto sigue esa regla: la busqueda se decide aca, con comparaciones baratas, y el
resultado entra al tablero de sensores igual que las memorias. El modelo no
elige nada — se encuentra la respuesta ya servida.

EL DETECTOR ES LO QUE IMPORTA. Buscar cuesta 2.4 s medidos, que sobre un turno
de 5-8 s es enorme. Buscar de mas es peor que no buscar: agrega latencia a
turnos que no la necesitan y mete ruido en el contexto de un modelo chico que
ya se distrae solo. Por eso el detector es CONSERVADOR y prefiere no buscar
ante la duda: si no busca, Russ contesta como venia haciendolo.

SE BUSCA CON LA FRASE TAL CUAL, en español. Hubo una version que la traducia
al ingles primero, para que los snippets vinieran en el idioma del resto del
contexto. Salio caro y esta medido: a «quien es el maximo goleador del Real
Madrid» la busqueda en español devolvia, primer resultado, «Cristiano Ronaldo,
maximo goleador historico del Real Madrid»; la misma pregunta traducida a «who
is the top scorer of the real madrid» devolvia titulos sin un solo nombre
adentro, y Russ termino inventando «Maradona».

En temas hispanohablantes la version en español recupera muchisimo mejor, y el
idioma del snippet le importa poco al modelo, que es multilingue. Los snippets
pueden venir en español y la respuesta sale en ingles igual.
"""
import collections
import re
import threading
import time

from app.core import runtime

MAX_RESULTADOS = 3
CHARS_POR_RESULTADO = 180      # un snippet largo se come el contexto y no aporta
TIMEOUT_S = 6                  # antes que colgar un turno, se contesta sin web

# Pedidos explicitos. Si dice "busca", no hay nada que interpretar.
EXPLICITO = re.compile(
    r'\b(busca(?:me|r)?|googlea|google|averigua|fijate en internet|'
    r'search|look up)\b', re.I)

# Preguntas por hechos del mundo. Van con \b y en orden de mas especifico a
# menos, y NINGUNA de ellas matchea "como estas" ni "que haces" — se probo.
FACTUAL = re.compile(
    r'\b(quien (?:es|fue|era|invento|escribio|gano)|'
    r'que (?:es|fue|significa|paso con|paso en)|'
    r'cuando (?:es|fue|nacio|murio|sale|empieza)|'
    r'donde (?:queda|esta|nacio)|'
    r'cuanto (?:cuesta|vale|mide|pesa|dura)|'
    # `cual es el/la <lo que sea>`, no una lista cerrada de sustantivos.
    # La version anterior enumeraba capital|poblacion|precio|record y
    # «cual es el presidente de colombia» no disparaba: contesto de memoria
    # y dijo primero Ivan Duque y despues se corrigio sola. Enumerar
    # sustantivos es una lista que nunca termina; el veto de `NUNCA` ya
    # cubre el caso peligroso, que es «cual es tu color favorito».
    r'cual (?:es|fue|era|son|seria) (?:el|la|los|las)\s+\w+|'
    r'noticias|ultimas noticias|que se sabe de)\b', re.I)

# Lo que NUNCA se busca aunque parezca pregunta factual: lo que trata sobre el
# propio Russ o sobre lo que tiene delante. "que es eso" mirando un objeto se
# contesta con la camara, no con Google.
NUNCA = re.compile(
    r'\b(vos|tu|tuyo|tuya|te |me |mi |nos )\b.*\b(sentis|sientes|pensas|piensas|'
    r'gusta|parece|acordas|recordas|recuerdas|ves|escuchas|llamas)\b|'
    r'\bque (?:es|son) (?:eso|esto|aquello)\b', re.I)

_estado = {"busquedas": 0, "ultima": "", "ms": 0, "error": None,
           "resultados": 0}

# Las ultimas busquedas CON SUS TEXTOS. Sin esto no hay forma de saber de quien
# fue la culpa cuando Russ dice una barbaridad: si el snippet estaba mal o si lo
# tenia bien delante y contesto otra cosa.
#
# Paso de verdad y es el motivo de que esto exista. A «quien es el maximo
# goleador del Real Madrid» la web devolvio, en el primer resultado, «Cristiano
# Ronaldo, maximo goleador historico del Real Madrid» — y Russ contesto Alfredo
# di Stefano. Sin el texto guardado eso se ve igual que una busqueda mala, y se
# arregla en lados opuestos: una es el detector o el buscador, la otra es el
# modelo y no tiene arreglo por codigo.
#
# Solo en memoria y solo las ultimas: es para depurar en caliente, no un
# archivo historico. A la DB no va porque no es conocimiento de Russ, es
# telemetria.
HISTORIAL_MAX = 12
_historial: collections.deque = collections.deque(maxlen=HISTORIAL_MAX)
_lock = threading.Lock()


def hace_falta(texto: str) -> bool:
    """Si esta frase se contesta mejor con la web que sin ella.

    Barato a proposito: son tres regex. Cualquier cosa mas cara aca —un
    clasificador, una llamada al modelo— gastaria en TODOS los turnos para
    decidir sobre unos pocos.
    """
    t = (texto or "").strip()
    if len(t) < 8 or not runtime.activo("busqueda"):
        return False
    if NUNCA.search(t):
        return False
    return bool(EXPLICITO.search(t) or FACTUAL.search(t))


def buscar(consulta: str) -> list:
    """Los primeros resultados, o lista vacia si algo falla.

    Nunca lanza: quedarse sin internet no puede costar un turno. Si no hay red,
    Russ contesta con lo que sabe, que es como funcionaba hasta ayer.
    """
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    try:
        t0 = time.time()
        from ddgs import DDGS
        with DDGS(timeout=TIMEOUT_S) as d:
            crudos = list(d.text(consulta, max_results=MAX_RESULTADOS))
        salida = []
        for r in crudos[:MAX_RESULTADOS]:
            cuerpo = " ".join((r.get("body") or "").split())
            if cuerpo:
                salida.append({"titulo": (r.get("title") or "").strip(),
                               "texto": cuerpo[:CHARS_POR_RESULTADO],
                               "url": r.get("href") or ""})
        ms = int((time.time() - t0) * 1000)
        with _lock:
            _estado.update(busquedas=_estado["busquedas"] + 1,
                           ultima=consulta[:100], ms=ms,
                           resultados=len(salida), error=None)
            _historial.appendleft({
                "cuando": time.strftime("%H:%M:%S"),
                "consulta": consulta, "ms": ms, "resultados": salida})
        return salida
    except Exception as e:
        with _lock:
            _estado["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        return []


def para_el_tablero(resultados: list) -> str:
    """Los resultados en una linea del tablero, con la misma forma que el resto.

    Sin URLs: no las puede abrir, no las puede leer en voz alta y ocupan un
    tercio del presupuesto de caracteres. Quedan en `/api/busqueda/estado` para
    quien quiera auditar de donde salio algo.
    """
    if not resultados:
        return ""
    piezas = [f"{r['titulo']}: {r['texto']}" if r["titulo"] else r["texto"]
              for r in resultados]
    return "Web says: " + " | ".join(piezas)


def historial() -> list:
    """Las ultimas busquedas con sus textos, la mas nueva primero."""
    with _lock:
        return list(_historial)


def estado() -> dict:
    with _lock:
        return dict(_estado, activo=runtime.activo("busqueda"),
                    historial=list(_historial))
