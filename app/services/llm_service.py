"""Elige el motor del asistente. Los dos exponen la misma interfaz:
`generar(mensajes, al_token)`, `cargar()`, `descargar()`, `estado()`.

    JARVIS_LLM=0.6b | 1.7b | 4b   -> Qwen3 local sobre llama.cpp
    JARVIS_LLM=groq               -> llama-3.3-70b por API

Que sea una variable y no una decision de codigo es a proposito: el local y el
remoto sirven para cosas distintas y conviene poder cambiar sin tocar nada.
"""
import os

from dotenv import load_dotenv

from app.services import llm_groq, llm_local

load_dotenv()


def motor():
    return llm_groq if os.environ.get("JARVIS_LLM", "").lower() == "groq" else llm_local


def generar(mensajes: list, al_token=None, gbnf: str | None = None,
            gbnf_cont: str | None = None, pensamiento: str = "") -> str:
    """`gbnf` solo lo entiende el motor local (llama.cpp). Contra Groq se
    ignora en silencio: la API no acepta gramaticas, y romper por eso dejaria
    al asistente mudo por una funcion opcional.

    `gbnf_cont` es la gramatica con la que RETOMA si se le corto el
    pensamiento por tope. Va junto con `gbnf` o no va."""
    if motor() is llm_local:
        return motor().generar(mensajes, al_token=al_token, gbnf=gbnf,
                               gbnf_cont=gbnf_cont, pensamiento=pensamiento)
    return motor().generar(mensajes, al_token=al_token)


def soporta_gramatica() -> bool:
    return motor() is llm_local


def piensa_abierto() -> bool:
    """True si el prompt ya deja el <think> abierto con un prefijo escrito.
    Cambia que gramatica corresponde: lo que el modelo genera arranca DENTRO
    del bloque, no antes de el."""
    return motor() is llm_local and bool(llm_local._prefijo())


def cargar():
    return motor().cargar()


def descargar():
    return motor().descargar()


def estado() -> dict:
    return motor().estado()
