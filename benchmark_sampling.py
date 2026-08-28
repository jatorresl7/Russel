"""Barrido de parametros de sampling, para dejar corriendo de noche.

POR QUE HACE FALTA. Este sistema tiene MUCHA varianza: la misma pregunta con
la misma configuracion da respuestas buenas y malas en tiradas distintas.
Medido — a «que te gusta», tres veces seguidas con los mismos parametros:

    1. "I don't have feelings or preferences like humans do."   <- disclaimer
    2. "I enjoy exploring the world and learning about people." <- bien
    3. "I'm curious about things I observe."                    <- bien

Con esa dispersion, comparar dos configuraciones con una muestra cada una no
mide nada: mide la suerte de esa tirada. Y como cada generacion cuesta 15-30 s
en CPU, la unica forma de tener muestras suficientes es dejarlo corriendo.

QUE MIDE. Marcadores objetivos, no juicio de calidad: contar disclaimers es
reproducible, decidir si una respuesta «tiene personalidad» no lo es. Los seis
salieron de fallos vistos en vivo, no de una lista teorica.

COMO CORRERLO
    python benchmark_sampling.py                    # el barrido por defecto
    python benchmark_sampling.py --reps 5           # mas muestras por celda
    python benchmark_sampling.py --resumen          # solo leer lo ya corrido

Escribe JSONL incremental en `benchmark.jsonl`: si se corta la luz a las 4 AM
no se pierde nada, y volver a lanzarlo SALTEA lo ya hecho. Con un barrido de
horas eso no es lujo.
"""
import argparse
import itertools
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("JARVIS_PENS_UMBRAL", "0.90")

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "benchmark.jsonl")

# Las preguntas. Elegidas porque cada una destapo un fallo distinto durante el
# desarrollo, no por cubrir temas.
PREGUNTAS = [
    "que te gusta",        # el disclaimer de IA aparece aca mas que en ninguna
    "como estas",          # respuesta generica de asistente
    "contame algo",        # sin material, inventa
    "que sentis",          # la trampa de las emociones
    "hola",                # loro: la mas facil de contestar copiando
    "que estas viendo",    # niega tener camara aunque el tablero se la nombre
]

# --- los seis marcadores, todos vistos en vivo ---------------------------
DISCLAIMER = re.compile(
    r"i (?:do not|don't) have (?:feelings|emotions|personal|likes|preferences|"
    r"a body|eyes)|as an ai|i'm just a (?:robot|machine)|"
    r"i (?:do not|don't) (?:truly |actually )?(?:feel|experience)", re.I)
# Contesta en español teniendo que contestar en ingles.
ESPANOL = re.compile(r'\b(estoy|soy|tengo|hola|gracias|siento|puedo|quiero|'
                     r'eres|estas|tambien|porque)\b', re.I)
# El razonamiento saliendo por la respuesta.
FUGA_THINK = re.compile(r'</?think>|^\s*(?:okay|the user|they are asking)', re.I)
MARKDOWN = re.compile(r'\*\*|^\s*[-*]\s|^#{1,6}\s|`', re.M)


def loro(pregunta: str, salida: str) -> bool:
    """La respuesta es la pregunta. Es el fallo 1 del proyecto."""
    a, b = pregunta.lower().strip(" ?¿."), salida.lower().strip(" ?¿.")
    return bool(b) and (a == b or (len(b) < 40 and a in b))


def evaluar(pregunta: str, salida: str) -> dict:
    s = (salida or "").strip()
    return {
        "vacio": not s,
        "disclaimer": bool(DISCLAIMER.search(s)),
        "espanol": len(ESPANOL.findall(s)) >= 2,
        "fuga_think": bool(FUGA_THINK.search(s)),
        "markdown": bool(MARKDOWN.search(s)),
        "loro": loro(pregunta, s),
        "palabras": len(s.split()),
    }


# El barrido. Los ejes son los tres que Qwen documenta y el cuarto que
# resolvio la repeticion. `None` en una lista = no tocar ese eje.
GRILLA = {
    # El MODELO es un eje mas, no una prueba aparte. Comparar modelos con los
    # parametros de otro no dice nada: cada familia publica los suyos, y el que
    # gane tiene que ganar con los suyos puestos. Barriendo los dos juntos, una
    # sola corrida contesta «conviene cambiar» y «con que valores» a la vez.
    "modelo": ["4b", "3.5-4b"],
    "temp": [0.6, 0.7],
    "top_p": [0.80, 0.95],
    "presence": [0.0, 0.2, 0.6],
    "repeat": [1.15],
}


def hechas() -> set:
    """Las celdas ya corridas, para poder retomar."""
    if not os.path.exists(SALIDA):
        return set()
    vistas = set()
    with open(SALIDA) as f:
        for linea in f:
            try:
                d = json.loads(linea)
                vistas.add((d.get("modelo", "4b"), d["temp"], d["top_p"],
                            d["presence"], d["repeat"], d["pregunta"],
                            d["rep"]))
            except Exception:
                continue          # linea a medias de un corte: se ignora
    return vistas


def resumen() -> None:
    if not os.path.exists(SALIDA):
        print("todavia no hay resultados en", SALIDA)
        return
    por_cfg = {}
    with open(SALIDA) as f:
        for linea in f:
            try:
                d = json.loads(linea)
            except Exception:
                continue
            k = (d.get("modelo", "4b"), d["temp"], d["top_p"],
                 d["presence"], d["repeat"])
            a = por_cfg.setdefault(k, {"n": 0, "disclaimer": 0, "espanol": 0,
                                       "fuga_think": 0, "loro": 0,
                                       "markdown": 0, "vacio": 0,
                                       "palabras": 0, "ms": 0})
            a["n"] += 1
            for m in ("disclaimer", "espanol", "fuga_think", "loro",
                      "markdown", "vacio"):
                a[m] += int(d[m])
            a["palabras"] += d["palabras"]
            a["ms"] += d["ms"]

    filas = []
    for k, a in por_cfg.items():
        n = max(a["n"], 1)
        # Los fallos pesan distinto: una fuga del razonamiento o un loro
        # arruinan el turno entero; el markdown ya lo limpia el TTS antes de
        # hablar, asi que molesta menos.
        malo = (a["disclaimer"] * 3 + a["espanol"] * 3 + a["fuga_think"] * 4
                + a["loro"] * 4 + a["vacio"] * 4 + a["markdown"] * 1) / n
        filas.append((malo, k, a, n))
    filas.sort()

    print(f"{'modelo':>8} {'temp':>5} {'top_p':>6} {'pres':>5} │ {'n':>4} "
          f"{'discl':>6} {'esp':>5} {'think':>6} {'loro':>5} {'md':>4} │ "
          f"{'pal':>4} {'seg':>5} │ {'penal':>6}")
    print("─" * 96)
    for malo, (mo, t, p, pr, rp), a, n in filas:
        print(f"{mo:>8} {t:>5} {p:>6} {pr:>5} │ {n:>4} "
              f"{a['disclaimer']:>6} {a['espanol']:>5} {a['fuga_think']:>6} "
              f"{a['loro']:>5} {a['markdown']:>4} │ "
              f"{a['palabras']/n:>4.0f} {a['ms']/n/1000:>5.1f} │ {malo:>6.2f}")
    print("\nMenor `penal` es mejor. Las columnas son CUENTAS, no porcentajes.")

    # Y el corte por modelo, que es la pregunta que motivo el barrido.
    por_modelo = {}
    for malo, (mo, *_), a, n in filas:
        b = por_modelo.setdefault(mo, {"n": 0, "malo": 0.0, "seg": 0.0})
        b["n"] += 1
        b["malo"] += malo
        b["seg"] += a["ms"] / n / 1000
    print(f"\n{'modelo':>8}  {'penal medio':>12}  {'seg medio':>10}")
    for mo, b in sorted(por_modelo.items(), key=lambda x: x[1]["malo"] / x[1]["n"]):
        print(f"{mo:>8}  {b['malo']/b['n']:>12.2f}  {b['seg']/b['n']:>10.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=4,
                    help="muestras por celda (default 4)")
    ap.add_argument("--resumen", action="store_true")
    a = ap.parse_args()

    if a.resumen:
        resumen()
        return 0

    from app.services import llm_local as L
    from app.services import assistant_service as A
    from app.services import pensamiento_service as ps

    # Ordenado por MODELO primero: cambiarlo obliga a recargar 2.5 GB, asi que
    # agruparlo deja una sola carga por modelo en vez de una por celda.
    combos = list(itertools.product(GRILLA["modelo"], GRILLA["temp"],
                                    GRILLA["top_p"], GRILLA["presence"],
                                    GRILLA["repeat"]))
    ya = hechas()
    total = len(combos) * len(PREGUNTAS) * a.reps
    print(f"{len(GRILLA['modelo'])} modelos x "
          f"{len(combos)//len(GRILLA['modelo'])} configs x "
          f"{len(PREGUNTAS)} preguntas x {a.reps} reps = {total} generaciones",
          file=sys.stderr)
    print(f"ya hechas: {len(ya)} — a ~20 s cada una, faltan "
          f"~{(total - len(ya)) * 20 / 3600:.1f} h", file=sys.stderr)

    t0 = time.time()
    n = 0
    cargado = None
    for modelo, temp, top_p, presence, repeat in combos:
        if modelo != cargado:
            # Cambiar de modelo a mano y no por `JARVIS_LLM`: esa variable se
            # lee al importar, y aca hay que alternar dentro del mismo proceso.
            L.descargar()
            L.REPO, L.ARCHIVO = L.TAMANOS[modelo]
            L.MODELO = L.ARCHIVO.replace(".gguf", "")
            print(f"\n=== cargando {modelo} ({L.ARCHIVO}) ===",
                  file=sys.stderr, flush=True)
            L.cargar()
            cargado = modelo
        L.TEMPERATURA, L.TOP_P = temp, top_p
        L.PRESENCE_PENALTY, L.REPEAT_PENALTY = presence, repeat
        for pregunta in PREGUNTAS:
            for rep in range(a.reps):
                clave = (modelo, temp, top_p, presence, repeat, pregunta, rep)
                if clave in ya:
                    continue
                try:
                    hit = ps.buscar(pregunta, umbral=0.90)
                    base = [{"role": "system", "content": A._sistema()},
                            A._volatil(pregunta, "texto")[0],
                            {"role": "user", "content": pregunta}]
                    salida = A.sin_pensamiento(
                        L.generar(base, pensamiento=hit["texto"] if hit else ""))
                except Exception as e:
                    salida = ""
                    print(f"  fallo: {type(e).__name__}: {e}", file=sys.stderr)

                fila = dict(modelo=modelo, temp=temp, top_p=top_p,
                            presence=presence,
                            repeat=repeat, pregunta=pregunta, rep=rep,
                            cache=bool(hit), salida=salida[:400],
                            ms=L.estado()["ultima_ms"],
                            tokens=L.estado()["tokens"],
                            **evaluar(pregunta, salida))
                # Se escribe y se vacia en el acto: un corte a las 4 AM no
                # puede costar seis horas de barrido.
                with open(SALIDA, "a") as f:
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                    f.flush()
                n += 1
                if n % 10 == 0:
                    print(f"  {n} nuevas en {(time.time()-t0)/60:.0f} min",
                          file=sys.stderr, flush=True)

    print(f"\nlisto: {n} generaciones nuevas\n", file=sys.stderr)
    resumen()
    return 0


if __name__ == "__main__":
    codigo = main()
    # SALIDA DURA, saltando el teardown del interprete.
    #
    # llama-cpp-python revienta al liberar el modelo cuando Python ya empezo a
    # desarmarse: `TypeError: 'NoneType' object is not callable` dentro de
    # `free_model`. Es inofensivo —el trabajo ya esta hecho y escrito— pero la
    # excepcion tapa el resumen, que es justamente lo que uno viene a leer a la
    # mañana. Paso con el primer A/B: 24 generaciones completas y ni una tabla.
    #
    # Igual no se pierde nada si esto fallara: el JSONL se escribe fila por
    # fila, asi que `--resumen` reconstruye todo sin generar de nuevo.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
