"""Lo que Russ puede hacer, y nada mas.

Este registro es DELIBERADAMENTE corto y no incluye nada que ejecute comandos.
La tabla `tools` de la DB guarda scripts de shell que corren con `shell=True`;
eso esta bien mientras el que elige es una persona desde la UI, y deja de
estarlo en cuanto elige un 4B cuantizado. Russ no la ve.

La regla, que hay que sostener aunque incomode: el modelo NUNCA compone un
comando. Elige un nombre de este registro cerrado y rellena argumentos tipados
que la gramatica ya restringio. Si una herramienta necesita algo que no se
puede acotar en la gramatica, esa herramienta todavia no esta lista para que la
llame Russ.
"""
import json

from app.services import memoria_service, vision_service

# ── Implementaciones ────────────────────────────────────────────────────────

def _recordar(texto: str = "", tipo: str = "hecho", **_) -> str:
    r = memoria_service.guardar(texto, tipo=tipo, fuente="explicito")
    if r.get("guardada"):
        return "guardado"
    return f"no se guardo: {r.get('motivo', 'sin motivo')}"


def _mirar(**_) -> str:
    v = vision_service.lo_que_veo()
    if not v["viva"]:
        return "la camara no esta entregando imagen"
    return v["texto"]


# ── Registro ────────────────────────────────────────────────────────────────
# `gbnf` es el cuerpo literal del objeto JSON de cada tool. Al ser literal, el
# modelo solo tiene que rellenar los huecos: es lo mas facil que se le puede
# poner delante, y por eso es lo mas confiable en CPU.
TOOLS = {
    "recordar": {
        "fn": _recordar,
        "gesto": "guardar algo",
        "descripcion": "Guarda algo para acordarte despues.",
        "pedido": lambda a, r: (f'(guardaste esto: "{a.get("texto", "")}") '
                                f'Decile que ya lo tenes.'),
        "gbnf": '"{\\"name\\":\\"recordar\\",\\"texto\\":" cadena ",\\"tipo\\":" tipo "}"',
    },
    # `mirar` SE SACO del registro, y `_mirar()` queda solo para uso manual.
    #
    # Era redundante y ademas rompia respuestas: `_volatil()` ya le mete "Ahora
    # mismo por la camara ves: X" en TODOS los turnos, asi que la tool le
    # devolvia lo que ya tenia delante. Visto en vivo: a "como estas" contesto
    # "Veo a Jaime" — habia razonado bien ("puedo decir que soy un robot") y
    # aun asi llamo a la tool y tiro por la borda su propia respuesta.
    #
    # Un modelo chico con una herramienta a mano la usa; la unica forma segura
    # de que no la use cuando no toca es que no exista. Y de paso se ahorra la
    # segunda pasada del modelo, que son segundos.
}


def gramatica(pensar: bool = True, modo: str | None = None) -> str:
    """GBNF que permite texto libre O una llamada bien formada, nada mas.

    Despues del pensamiento la raiz es una alternancia: en cuanto el modelo
    emite un caracter que no es `<` queda en la rama de texto y ya no puede
    volver; y en cuanto emite `<` queda obligado a completar una llamada valida
    hasta el cierre.

    El `<think>` opcional adelante NO es decorado: sin el, esta gramatica le
    PROHIBE pensar. `libre` empieza por `[^<]`, asi que el unico `<` permitido
    era el de `<tool_call>` — con el modo thinking prendido el modelo quedaba
    obligado a llamar una tool o a no pensar. Adentro tampoco puede haber `<`,
    y eso esta bien: es prosa, no markup.
    """
    ramas = " | ".join(f"c-{n}" for n in TOOLS)
    reglas = "\n".join(f'c-{n} ::= {t["gbnf"]}' for n, t in TOOLS.items())
    # Tres modos, porque la gramatica solo restringe lo que el modelo GENERA y
    # eso depende de que le hayamos dejado ya escrito en el prompt:
    #
    #   libre    el prompt termina en "assistant\\n". Puede abrir <think> o no.
    #   abierto  el prompt ya trae "<think>\\n" + el prefijo escrito por nosotros.
    #            Lo que genera arranca DENTRO del bloque, asi que lo primero
    #            que tiene permitido es seguir pensando y cerrar con </think>.
    #   sin      se le cerro el pensamiento a la fuerza por tope. Dejarlo abrir
    #            otro <think> seria dejarlo pensar justo despues de pararlo.
    #   texto    turno con pensamiento cacheado: solo prosa, sin rama de tool.
    #            Un 4B con una herramienta a la vista la usa aunque no venga al
    #            caso — a "que ves ahora mismo" llamo a `recordar` y guardo el
    #            ejemplo del catalogo palabra por palabra. Los turnos que el
    #            cache reconoce son justamente los conversacionales, donde no
    #            hay nada que guardar; los novedosos siguen con tools.
    modo = modo or ("libre" if pensar else "sin")
    raiz = {"libre":   "piensa? cuerpo",     # puede abrir <think> o no
            "abierto": "resto cuerpo",       # el <think> YA viene en el prompt
            "sin":     "cuerpo",
            "texto":   "libre"}[modo]        # ni siquiera puede llamar una tool
    return f'''root ::= {raiz}
cuerpo ::= libre | llamada
piensa ::= "<think>" [^<]* "</think>" [ \\n]*
resto ::= [^<]* "</think>" [ \\n]*
libre ::= [^<] [^<]*
llamada ::= "<tool_call>" ( {ramas} ) "</tool_call>"
{reglas}
tipo ::= "\\"hecho\\"" | "\\"episodio\\""
cadena ::= "\\"" car* "\\""
car ::= [^"\\\\] | "\\\\" ["\\\\/bfnrt]
'''


# La forma EXACTA de cada llamada. Se la mostramos literal y no descrita.
#
# Medido en este proyecto: con el catalogo solo en prosa ("podes usar estas
# herramientas: recordar, mirar"), Qwen3-4B pidiendole "acordate de que mi
# hermana se llama Laura" contesto en texto plano — "Recuerdo: mi hermana se
# llama Laura" — sin llamar a nada. La gramatica garantiza que una llamada
# salga BIEN FORMADA; no hace que el modelo DECIDA llamar. Eso lo decide el
# prompt, y a un 4B sin modo thinking hay que darle el molde ya escrito.
#
# Cuesta ~60 tokens, pero van en el `system`, que es prefijo fijo y por lo
# tanto se cachea: se pagan una vez por sesion, no una vez por turno.
# OJO CON LOS NOMBRES DEL EJEMPLO. Este decia "Laura es la hermana de Jaime y
# vive en Medellin", y con el modo thinking prendido se filtro al razonamiento:
# arrancando solo por "aparecio Jaime", Russ se puso a pensar "What is the name
# of Jaime's sister? I know that from the previous conversation" — leyo el
# ejemplo de la tool como si fuera algo que habia vivido.
#
# Un ejemplo tiene que ser reconociblemente un ejemplo. Nombres que no son de
# nadie de esta casa y un dato que no se puede confundir con memoria propia.
EJEMPLOS_LLAMADA = {
    "recordar": '<tool_call>{"name":"recordar","texto":"el reloj de la cocina '
                'atrasa cinco minutos","tipo":"hecho"}</tool_call>',
}


def catalogo() -> str:
    """Lo que va en el prompt de sistema. Va ahi y no en el mensaje volatil
    porque no cambia entre turnos: tiene que ser parte del prefijo cacheado.

    OJO CON LA REDACCION. La primera version decia "tu respuesta es SOLO la
    llamada: sin saludo, sin explicacion, sin ninguna otra palabra antes ni
    despues". Las llamadas salian perfectas y la conversacion se destruyo: a
    "si ese soy yo" contestaba "si ese soy yo", a "que haces" contestaba
    "Jaime." — el fallo #1 de la lista de arriba de este proyecto, loro-repetir
    la entrada porque repetirte es lo mas corto que sigue estando en tema. El
    modelo no entendio que la brevedad era solo para el caso de la tool: la
    aplico a todo.

    Lo que funciona, medido con las mismas cinco frases: describir la
    herramienta sin un solo imperativo de brevedad, y cerrar diciendo que lo
    demas es conversacion. Nada de "solo", "unicamente", "sin nada mas".
    """
    lineas = [f"Para {t['gesto']} escribis: {EJEMPLOS_LLAMADA[n]}"
              for n, t in TOOLS.items()]
    return ("Podes guardar cosas.\n"
            + "\n".join(lineas)
            + "\nEso es lo unico que se escribe asi. Lo demas es conversacion.")


def parsear(salida: str) -> dict | None:
    """Devuelve `{name, args}` si la salida es una llamada, o None si es texto.

    Se vuelve a validar aunque la gramatica ya lo garantice: la gramatica solo
    aplica con el motor local, y con Groq esta funcion recibe texto sin
    restringir.
    """
    s = salida.strip()
    if not (s.startswith("<tool_call>") and s.endswith("</tool_call>")):
        return None
    try:
        datos = json.loads(s[len("<tool_call>"):-len("</tool_call>")])
    except Exception:
        return None
    nombre = datos.pop("name", None)
    if nombre not in TOOLS:
        return None
    return {"name": nombre, "args": datos}


def pedido(llamada: dict, resultado: str) -> str:
    """Que se le pide al modelo en la SEGUNDA pasada, despues de correr la tool.

    Cada herramienta trae el suyo porque el generico no alcanza. Con
    "(usaste recordar y devolvio: guardado) contestame vos", Qwen3-4B salio con
    "Que haces ahora?" — un no-sequitur. Un modelo chico necesita que el pedido
    diga QUE confirmar, no solo que conteste; con el texto guardado delante,
    contesta sobre eso.
    """
    tool = TOOLS.get(llamada["name"], {})
    hacer = tool.get("pedido")
    if hacer:
        return hacer(llamada.get("args", {}), resultado)
    return f"(usaste {llamada['name']} y devolvio: {resultado}) Contestale en una frase."


def ejecutar(llamada: dict) -> str:
    """Corre la tool y devuelve texto corto. Corto importa: el resultado vuelve
    al prompt y cada token es ~55ms de espera."""
    tool = TOOLS.get(llamada["name"])
    if not tool:
        return "esa herramienta no existe"
    try:
        return str(tool["fn"](**llamada["args"]))[:400]
    except Exception as e:
        return f"fallo: {type(e).__name__}"
