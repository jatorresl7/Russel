"""Embebidos de texto locales, para la memoria de Russ.

Modelo: `intfloat/multilingual-e5-small`. 118M de parametros, 384 dimensiones,
multilingue de verdad (el espanol no es un anexo). Es de los mas chicos que
todavia entiende parafrasis: "donde trabajo" tiene que acercarse a "estoy en
Aixa" sin compartir una sola palabra, y ahi es donde los modelos de bolsa de
palabras se caen.

Local y no OpenAI a proposito: la memoria de Russ es lo mas personal que hay en
este proyecto, y mandarla a una API por 384 numeros no compensa.

Los prefijos de e5 NO son decorativos. El modelo se entreno con "query:" para
lo que se busca y "passage:" para lo que se guarda, y usarlos al reves —o no
usarlos— degrada la busqueda de forma medible. Por eso hay dos funciones y no
una con un booleano: es mas dificil equivocarse.
"""
import threading
import time

import numpy as np

from app.core import runtime

MODELO = "intfloat/multilingual-e5-small"
DIMS = 384

_modelo = None
_lock_carga = threading.Lock()
_lock_uso = threading.Lock()      # el modelo no es seguro entre hilos
_estado = {"modelo": MODELO, "dims": DIMS, "cargado": False,
           "ultimo_ms": 0, "total": 0, "error": None}


def cargar():
    global _modelo
    with _lock_carga:
        if _modelo is not None:
            return _modelo
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(MODELO, device=runtime.device())
        # sentence-transformers usa torch por debajo; el limite de hilos es
        # global al proceso, asi que se pone aca y no en el constructor.
        try:
            import torch
            torch.set_num_threads(runtime.hilos("embed"))
        except Exception:
            pass
        _estado["cargado"] = True
        return _modelo


def descargar() -> dict:
    """Libera la RAM. La memoria deja de poder buscar hasta que se recargue."""
    global _modelo
    with _lock_carga:
        _modelo = None
        _estado["cargado"] = False
    return estado()


def _embeber(textos: list[str]) -> np.ndarray:
    modelo = cargar()
    t0 = time.time()
    with _lock_uso:
        vs = modelo.encode(textos, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    _estado["ultimo_ms"] = int((time.time() - t0) * 1000)
    _estado["total"] += len(textos)
    return vs.astype(np.float32)


def de_consulta(texto: str) -> list[float]:
    """Vector de algo que se BUSCA."""
    return _embeber([f"query: {texto}"])[0].tolist()


def de_memoria(texto: str) -> list[float]:
    """Vector de algo que se GUARDA."""
    return _embeber([f"passage: {texto}"])[0].tolist()


def de_memorias(textos: list[str]) -> list[list[float]]:
    """Varias de una. Bastante mas rapido que una por una: el costo esta en
    armar el lote, no en cada texto."""
    if not textos:
        return []
    return [v.tolist() for v in _embeber([f"passage: {t}" for t in textos])]


def disponible() -> bool:
    """Si se puede embeber ahora mismo. Con `embed` apagado la memoria sigue
    pudiendo listar y borrar, pero no guardar ni buscar."""
    return runtime.activo("embed")


def estado() -> dict:
    return dict(_estado, activo=runtime.activo("embed"),
                hilos=runtime.hilos("embed"))
