"""Los sonidos de fabrica de Russ, sintetizados aca mismo.

No se bajan de ningun lado: son ondas armadas con la libreria estandar. Asi el
panel de sonidos arranca con algo que suena en vez de con seis casillas vacias,
y no hay que meter binarios de dudoso origen en el repo.

Van afinados a una escala pentatonica y con envolvente suave en los bordes: un
tono cuadrado crudo hace clic al empezar y al terminar, y ese clic es lo que
separa "un robot" de "un error de sistema".
"""
import math
import os
import struct
import wave

SR = 22050
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos")

# Do-Re-Mi-Sol-La en la cuarta y quinta octava. Pentatonica: cualquier par de
# notas suena bien junto, asi que no hay forma de que un sonido quede disonante.
NOTAS = {"do": 523.25, "re": 587.33, "mi": 659.25, "sol": 783.99,
         "la": 880.00, "do5": 1046.50, "mi5": 1318.51, "sol5": 1567.98}


def tono(freq: float, ms: int, vol: float = 0.32) -> list:
    """Onda con un poco de segundo armonico —le da cuerpo de juguete— y
    envolvente de 8 ms en cada punta para que no chasquee."""
    n = int(SR * ms / 1000)
    subida = int(SR * 0.008)
    out = []
    for i in range(n):
        t = i / SR
        s = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
        env = min(1.0, i / subida, (n - i) / subida)
        out.append(s * env * vol / 1.25)
    return out


def silencio(ms: int) -> list:
    return [0.0] * int(SR * ms / 1000)


def escribir(nombre: str, muestras: list) -> None:
    os.makedirs(DIR, exist_ok=True)
    ruta = os.path.join(DIR, nombre + ".wav")
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in muestras))
    print(f"  {nombre + '.wav':16} {os.path.getsize(ruta) / 1024:5.1f} KB")


N = NOTAS
SONIDOS = {
    # Sube: algo se encendio y esta disponible.
    "despierta":  tono(N["do"], 90) + tono(N["mi"], 90) + tono(N["sol5"], 160),
    # Dos golpecitos iguales y bajos. Tiene que poder sonar seguido sin cansar.
    "pensando":   tono(N["re"], 55, 0.18) + silencio(70) + tono(N["re"], 55, 0.18),
    # Un solo blip alto y corto: "te escucho", sin robar la palabra.
    "escuchando": tono(N["la"], 70, 0.22),
    # Resuelve hacia arriba, corto. Es el mas frecuente: no puede molestar.
    "listo":      tono(N["sol"], 70) + tono(N["do5"], 110),
    # Baja dos veces. Sin estridencia — es un aviso, no una alarma.
    "error":      tono(N["mi"], 110, 0.26) + tono(N["do"], 170, 0.26),
    # Baja y se apaga.
    "duerme":     tono(N["sol"], 110) + tono(N["mi"], 110) + tono(N["do"], 200),
    # «Ya lo tengo». Suena JUSTO antes de la respuesta, asi que es el mas
    # frecuente de todos y el que mas rapido cansaria: por eso es el mas corto
    # (190 ms en total) y el mas bajo de volumen. Tres notas subiendo rapido,
    # sin la nota larga del final que tiene `despierta` — no es una llegada,
    # es un «ah» antes de hablar.
    "eureka":     tono(N["mi"], 55, 0.24) + tono(N["sol"], 55, 0.24)
                  + tono(N["do5"], 80, 0.26),
}

if __name__ == "__main__":
    print(f"sonidos en {DIR}/")
    for nombre, muestras in SONIDOS.items():
        escribir(nombre, muestras)
