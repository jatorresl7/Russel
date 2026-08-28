"""El profesor: Gemini escribe pensamientos, nosotros los revisamos y sembramos.

POR QUE UN MODELO GRANDE ESCRIBE LO QUE PIENSA UNO CHICO. El pensamiento no se
genera en caliente — se PREGUARDA. Se escribe una vez, se vectoriza y queda en
la tabla `pensamientos`; en el turno real solo hay una busqueda por similitud.
Asi que el costo de escribirlo bien se paga una sola vez y fuera de linea,
mientras que el beneficio se cobra en cada turno que acierte. Es el unico lugar
del sistema donde conviene gastar un modelo caro.

MEDIDO, y es el motivo de que esto exista. Con el cache apagado
(`JARVIS_PENS_UMBRAL=2`) Qwen3-4B contesta "buenas" con "Hola, soy Russ. ¿En
que puedo ayudarte?" en 15-22 s. Con el cache prendido, "Buenos dias. ¿Que
tal?" en 11-13 s y la mitad de tokens. El pensamiento precargado no solo
acelera: es lo que le saca el rol de asistente de fabrica.

QUE SE LE INYECTA A GEMINI. Todo lo que un autor humano necesitaria saber:
quien es Russ (el system real, importado, no una copia que se desactualice),
que es un pensamiento y que NO es, las tres reglas de forma, los antipatrones
que ya se pagaron caro en este proyecto, y ejemplos reales del catalogo. Sin
eso devuelve consejos de asistente virtual, que es exactamente lo que venimos
a sacar.

USO:
    python generar_pensamientos.py --listar                # que situaciones ya hay
    python generar_pensamientos.py --tema "le preguntan por su infancia"
    python generar_pensamientos.py --huecos 8              # que Gemini proponga
    python generar_pensamientos.py --huecos 8 --escribir   # y los guarde
Sin `--escribir` no toca nada: imprime lo que haria.
"""
import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.llm import GeminiClient, GroqClient, OpenAIClient  # noqa: E402
from app.services import pensamientos_semilla as sem       # noqa: E402
from app.services.assistant_service import SISTEMA         # noqa: E402

SALIDA = "app/services/pensamientos_generados.py"

# El brief. Es el archivo entero: si esto queda flojo, lo que vuelve son
# consejos de asistente virtual con formato de pensamiento.
BRIEF = """Escribis material para el razonamiento interno de un robot que corre
con un modelo de lenguaje CHICO (Qwen3-4B, en CPU). No escribis respuestas: 
escribis el ARRANQUE del bloque <think> que el modelo lee como si ya lo hubiera
pensado el, y desde el cual sigue.

QUIEN ES EL ROBOT. Este es, literal, su prompt de sistema:
---
{sistema}
---

QUE ES UN PENSAMIENTO ACA.
Cuando a Russ le hablan, se busca por similitud semantica la frase mas parecida
entre las guardadas. Si alguna pega, su pensamiento se le precarga dentro de
<think> y el modelo continua desde ahi en vez de derivar la misma apertura por
enesima vez. Se guarda ANTES, nunca se genera en el momento.

Por eso el pensamiento tiene que ser GENERICO respecto de la situacion pero
ESPECIFICO respecto del enfoque. "Me estan preguntando por mi estado" sirve
siempre; "veo a Jaime con una camisa azul" seria mentira dos minutos despues.

LAS TRES REGLAS DE FORMA. Las tres se pagan caro si se rompen:

1. El pensamiento va en INGLES. Qwen razona en el idioma en que fue entrenado y
   este es el paso caro; no conviene hacerle pagar una traduccion. Lo que sale
   por el parlante sigue siendo español.
2. Nada volatil. Ningun pensamiento puede decir que ve, quien esta en cuadro,
   que hora es ni que recuerda. Eso se le inyecta aparte en cada turno.
   Precargar algo volatil lo haria mentir con conviccion.
3. Termina ABIERTO, sin punto final, o cerrado de forma que lo unico que pueda
   seguir sea el contenido real. Es un empujon, no un guion.

LOS DISPARADORES van en ESPAÑOL, porque contra ellos se compara lo que el
usuario dice. Cada pensamiento lleva 6 frases COMO MINIMO (contalas antes de responder;
menos de 6 se rechaza), variadas y cortas, como
las diria alguien hablando: con voseo y sin tildes tambien, porque entran por un
transcriptor de voz. NO metas varias ideas distintas en un mismo pensamiento:
cada fila es un vector, y un disparador que mezcla temas cae en el medio de
todos y no se parece a ninguno.

ANTIPATRONES. Todos estos ya se probaron en este proyecto y salieron mal:

- NO le pidas brevedad de forma imperativa ("responde solo", "se breve", "sin
  decir nada mas"). Un modelo chico la aplica a TODO y empieza a loro-repetir la
  entrada, porque repetirte es lo mas corto que sigue estando en tema.
- NO lo definas por lo que NO es. "No sos un asistente" le activa el rol de
  asistente. Se corrige diciendo que ES o que HACE, nunca negando.
- NO le pidas que ACTUE de algo ("sos curioso", "se simpatico"). Actua de eso, y
  se nota. Lo que produce curiosidad no es el adjetivo: es tener preguntas
  abiertas sobre algo que importa. Describi el estado de conocimiento, no el
  rasgo.
- NO acumules frenos. Un pensamiento con tres advertencias y ningun motivo da
  silencio: se probo "solo abro la boca si vale la pena" y contesto "no entiendo
  que hacer". Si va un freno, va uno solo y al final.
- NO enumeres sus partes ni sus capacidades. Cuando se le dio una descripcion de
  su cuerpo, se presentaba en vez de contestar.
- NO escribas un pensamiento que sea la respuesta. Es el enfoque de como
  encararla.

EJEMPLOS REALES del catalogo actual, para el tono y el largo:
{ejemplos}

SITUACIONES YA CUBIERTAS (no las repitas):
{cubiertas}

TU TAREA:
{tarea}

Devolves JSON y NADA mas — sin markdown, sin ```json, sin comentarios:
[{{"situacion": "<en español, 3-6 palabras, para que un humano lo revise>",
  "disparadores": ["<frase en español>", "..."],
  "pensamiento": "<en ingles, 2-4 oraciones, empezando por lo que esta pasando>"}}]
"""


def _ejemplos(n: int = 4) -> str:
    return "\n\n".join(
        f"disparadores: {', '.join(d[:5])}\npensamiento: {t}"
        for d, t in sem.SEMILLA[:n])


def _ya_generados() -> list:
    """Lo que hay en SALIDA de corridas anteriores, o vacio si no hay nada.

    Se lee para ACUMULAR. La primera version reescribia el archivo entero en
    cada corrida y se perdieron tres tandas buenas sin que nada lo avisara: el
    script decia "escrito" y era verdad, solo que tambien habia borrado.
    """
    try:
        from app.services.pensamientos_generados import GENERADOS
    except Exception:
        return []
    # La `situacion` no vive en la tupla, vive en el comentario de arriba. Sin
    # recuperarla, cada reescritura borraba las etiquetas de las tandas
    # anteriores y quedaban veinte entradas con `#` vacio, imposibles de
    # revisar de un vistazo.
    try:
        etiquetas = re.findall(r"^    # (.*)$", open(SALIDA).read(), re.M)
    except OSError:
        etiquetas = []
    return [{"situacion": etiquetas[i] if i < len(etiquetas) else "",
             "disparadores": list(d), "pensamiento": t}
            for i, (d, t) in enumerate(GENERADOS)]


def _cubiertas(extra: list) -> str:
    """Las situaciones que ya existen, a mano y generadas. Van al brief para
    que el profesor no vuelva a proponer lo mismo cada vez que se lo llama."""
    lineas = ["- " + ", ".join(d[:4]) for d, _ in sem.SEMILLA]
    lineas += ["- " + ", ".join(p["disparadores"][:4]) for p in extra]
    return "\n".join(lineas)


def _parsear(crudo: str) -> list:
    """Gemini igual mete ```json a veces, aunque se le pida que no."""
    t = crudo.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t).strip()
    i, j = t.find("["), t.rfind("]")
    if i == -1 or j == -1:
        raise ValueError(f"no vino JSON:\n{crudo[:400]}")
    return json.loads(t[i:j + 1])


# Los tres chequeos que un humano no deberia tener que hacer a ojo. No juzgan
# calidad —para eso esta la revision— sino las reglas de forma, que son
# mecanicas y que romperlas envenena el cache en silencio.
PROHIBIDAS = ("i see", "i can see", "right now i", "in front of me is",
              "the time is", "i remember that")

# El disclaimer de IA. Es el antipatron que MAS se cuela, porque es el default
# de cualquier modelo grande al que le preguntan por sentimientos: "no tengo
# gustos", "no siento de verdad", "como IA que soy". Precargar eso seria pagar
# un modelo caro para inyectarle a Russ justo el rol que venimos a sacarle.
DISCLAIMER = ("i do not have personal", "i don't have personal", "as an ai",
              "i do not truly", "i don't truly", "i cannot feel",
              "i can't feel", "i do not actually feel", "i simulate",
              "i am an ai", "i'm an ai", "i lack the ability",
              "i do not possess", "i have no sensors", "i do not experience")


def revisar(p: dict) -> list:
    fallas = []
    texto = (p.get("pensamiento") or "").strip()
    disp = p.get("disparadores") or []
    if not texto or not disp:
        fallas.append("vacio")
        return fallas
    # OJO: el docstring de `pensamientos_semilla` dice que los pensamientos
    # "terminan abiertos, sin punto final". Los 21 escritos a mano cierran
    # TODOS con punto. La regla del abierto es del `PREFIJO_PENSAMIENTO` de
    # `llm_local` ("...what they are actually asking is"), que es otra cosa:
    # ese se concatena al arranque del <think>, estos son el bloque. Aca no se
    # valida el punto final porque el catalogo real lo contradice.
    if len(disp) < 5:
        fallas.append(f"solo {len(disp)} disparadores (van 5-8)")
    bajo = texto.lower()
    if any(x in bajo for x in PROHIBIDAS):
        fallas.append("parece contener algo volatil")
    hay = [x for x in DISCLAIMER if x in bajo]
    if hay:
        fallas.append(f"disclaimer de IA — el antipatron: {hay[0]!r}")
    # Sin un punto en 2-4 oraciones el modelo se comio la puntuacion, y el
    # pensamiento se lee como un chorro. Visto con gpt-oss-120b.
    if texto.count(".") == 0 and len(texto.split()) > 15:
        fallas.append("sin puntuacion (el modelo se la comio)")
    if not re.search(r"[a-z]", texto):
        fallas.append("vacio de texto")
    # Un pensamiento en español seria un bug caro y silencioso.
    if re.search(r"\b(que|para|porque|cuando|estoy|tengo)\b", texto.lower()):
        fallas.append("parece escrito en español, va en ingles")
    return fallas


def como_python(items: list, profesor: str = "") -> str:
    filas = []
    for p in items:
        # `.get` y no `p[...]`: el profesor a veces omite un campo, y con
        # acceso directo saltaba KeyError DESPUES de que `open(..., "w")`
        # hubiera truncado el archivo. Asi se perdieron 9 pensamientos ya
        # guardados. El que venga incompleto se salta y ya.
        disparadores, texto = p.get("disparadores"), p.get("pensamiento")
        if not disparadores or not texto:
            continue
        disp = json.dumps(list(disparadores), ensure_ascii=False)
        txt = json.dumps(texto, ensure_ascii=False)
        filas.append(f"    # {p.get('situacion','')}\n    ({disp},\n     {txt}),")
    return (f'"""Pensamientos escritos por {profesor}, para revisar a mano.\n\n'
            'Generado por `generar_pensamientos.py`. Se puede volver a generar,\n'
            'asi que lo editado a mano aca se pierde: lo que valga la pena\n'
            'conservar va a `pensamientos_semilla.py`, que es el catalogo humano.\n'
            '"""\n\nGENERADOS = [\n' + "\n".join(filas) + "\n]\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tema", help="situacion concreta a cubrir")
    ap.add_argument("--huecos", type=int, help="que Gemini proponga N situaciones nuevas")
    ap.add_argument("--proveedor", default="gemini",
                    choices=("gemini", "groq", "openai"))
    ap.add_argument("--modelo", help="por defecto, el del proveedor")
    ap.add_argument("--escribir", action="store_true", help="guarda en " + SALIDA)
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()

    if a.listar:
        for d, _ in sem.SEMILLA:
            print(f"  {', '.join(d[:5])}")
        print(f"\n{len(sem.SEMILLA)} pensamientos, "
              f"{sum(len(d) for d, _ in sem.SEMILLA)} disparadores")
        return 0

    if a.tema:
        tarea = (f"Escribi UN pensamiento para esta situacion: {a.tema}")
    elif a.huecos:
        tarea = (
            f"Mira las situaciones ya cubiertas y proponé {a.huecos} que FALTEN.\n"
            "Buscá las que se le van a dar de verdad a un robot que vive en un\n"
            "escritorio y habla con la persona que lo construye — no situaciones\n"
            "de asistente virtual. Vale lo incomodo y lo personal.")
    else:
        print("falta --tema o --huecos (o --listar)", file=sys.stderr)
        return 2

    # Multi-proveedor porque el profesor es intercambiable: lo que importa es
    # que sea un modelo grande, no cual. Se escribe una vez y fuera de linea.
    cual = {"gemini": ("GEMINI_API_KEY", GeminiClient, "gemini-3.6-flash"),
            "groq": ("GROQ_API_KEY", GroqClient, "openai/gpt-oss-120b"),
            "openai": ("OPENAI_API_KEY", OpenAIClient, "gpt-4o")}[a.proveedor]
    var, Cliente, por_defecto = cual
    clave = os.environ.get(var)
    if not clave:
        print(f"falta {var} en el .env", file=sys.stderr)
        return 2
    a.modelo = a.modelo or por_defecto

    previos = _ya_generados()
    prompt = BRIEF.format(sistema=SISTEMA, ejemplos=_ejemplos(),
                          cubiertas=_cubiertas(previos), tarea=tarea)
    print(f"[{a.proveedor} {a.modelo}] {len(prompt)} chars de brief...",
          file=sys.stderr)
    crudo = Cliente(api_key=clave, model=a.modelo).generate(prompt)
    items = _parsear(crudo)

    for p in items:
        fallas = revisar(p)
        marca = "  OK  " if not fallas else "REVISAR"
        print(f"\n[{marca}] {p.get('situacion','?')}")
        if fallas:
            for f in fallas:
                print(f"         ! {f}")
        print(f"   disparadores: {', '.join(p.get('disparadores', []))}")
        print(f"   pensamiento : {p.get('pensamiento','')}")

    print(f"\n{len(items)} pensamientos generados.", file=sys.stderr)
    if a.escribir:
        # Acumular, no pisar. Se deduplica por disparador: si el profesor
        # repite una frase que ya existe, gana la que estaba.
        vistos = {d for p in previos for d in p["disparadores"]}
        nuevos = [p for p in items
                  if not (set(p.get("disparadores", [])) & vistos)]
        # El texto se arma ANTES de tocar el archivo, y se escribe a un
        # temporal que despues se renombra. `open(..., "w")` trunca en el acto,
        # asi que cualquier excepcion entre abrir y escribir deja el archivo
        # vacio — que es exactamente como se perdio una tanda entera.
        contenido = como_python(previos + nuevos, f"{a.proveedor} {a.modelo}")
        tmp = SALIDA + ".tmp"
        with open(tmp, "w") as f:
            f.write(contenido)
        os.replace(tmp, SALIDA)
        print(f"{len(previos)} previos + {len(nuevos)} nuevos "
              f"({len(items) - len(nuevos)} repetidos, descartados) -> {SALIDA}",
              file=sys.stderr)
        print("Para que entren: importalos en pensamientos_semilla.SEMILLA y\n"
              "reinicia — `asegurar_semilla()` re-siembra sola porque cambia la\n"
              "huella del catalogo.", file=sys.stderr)
    else:
        print("(nada escrito — agrega --escribir)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
