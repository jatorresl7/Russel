import { GlobalConfig } from '../../global-config';

const API = GlobalConfig.getInstance().apiUrl;

type Oyente = (ev: any) => void;

/**
 * Un solo `EventSource` para toda la página.
 *
 * `/assistant/stream` lleva la conversación Y los cambios del grafo, así que
 * mas de un componente los quiere. Abrir uno por componente costaría una
 * conexión PERMANENTE cada vez, y el navegador limita cuantas admite por
 * servidor (Firefox, 6) — con el MJPEG de la cámara ya son dos ocupadas para
 * siempre. Mismo motivo que `audio.store`, pero acá pesa mas: un SSE no se
 * cierra nunca por su cuenta.
 *
 * Todos reciben todo y cada uno filtra por `tipo`. Con la cantidad de eventos
 * que maneja esto —unos pocos por turno— repartir por tipo seria complicar sin
 * ganar nada.
 *
 * Se abre con el primer suscriptor y se cierra con el último. Cerrarlo importa
 * de verdad: un SSE abierto es lo que deja colgado el `--reload` de uvicorn.
 */
class SseStore {
  private _es?: EventSource;
  private _oyentes = new Set<Oyente>();

  suscribir(fn: Oyente): () => void {
    this._oyentes.add(fn);
    if (this._oyentes.size === 1) this._abrir();
    return () => {
      this._oyentes.delete(fn);
      if (!this._oyentes.size) {
        this._es?.close();
        this._es = undefined;
      }
    };
  }

  private _abrir() {
    this._es = new EventSource(API + 'assistant/stream');
    this._es.onmessage = e => {
      let ev: any;
      try { ev = JSON.parse(e.data); } catch { return; }
      this._oyentes.forEach(fn => fn(ev));
    };
  }
}

export const sseStore = new SseStore();
