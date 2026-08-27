import { AudioService, EstadoAudio, EstadoLlmBarra, VACIO } from './audio.service';

/** 400 ms es lo que hace que la barra de voz se sienta pegada a lo que estás
 *  diciendo. Más lento y el VAD se ve a saltos. */
const MS_SONDEO = 400;

const LLM_VACIO: EstadoLlmBarra =
  { activo: false, cargado: false, generando: false, modelo: '', tok_s: 0 };

export interface Instantanea { audio: EstadoAudio; llm: EstadoLlmBarra; }

type Oyente = (i: Instantanea) => void;

/**
 * Un solo sondeo de `/audio/status` y `/assistant/status` para toda la página.
 *
 * Antes cada componente traía el suyo, y en la vista unificada eso eran cuatro
 * peticiones cada 400 ms para leer dos endpoints. El navegador limita las
 * conexiones simultáneas por servidor —Firefox son 6— y en esta app dos ya
 * están tomadas PARA SIEMPRE: el MJPEG de la cámara y el SSE de la charla. Con
 * lo poco que queda, unos sondeos que se solapan alcanzan para que la interfaz
 * entera se vea congelada, que es exactamente igual a que el micrófono no ande.
 *
 * Además hay guarda de solapamiento: mientras una vuelta esté en vuelo no sale
 * otra. Cuando whisper corre su pasada final se lleva 9 hilos y el servidor
 * tarda; sin la guarda, `setInterval` sigue disparando y las peticiones se
 * apilan justo en el peor momento.
 *
 * Se arranca con el primer suscriptor y se apaga con el último: si nadie está
 * mirando, no se sondea.
 */
class AudioStore {
  private _svc = new AudioService();
  private _oyentes = new Set<Oyente>();
  private _timer?: number;
  private _enVuelo = false;

  ultima: Instantanea = { audio: VACIO, llm: LLM_VACIO };

  suscribir(fn: Oyente): () => void {
    this._oyentes.add(fn);
    if (this._oyentes.size === 1) {
      this._tick();
      this._timer = window.setInterval(() => this._tick(), MS_SONDEO);
    } else {
      fn(this.ultima);            // el que llega tarde no espera un ciclo
    }
    return () => {
      this._oyentes.delete(fn);
      if (!this._oyentes.size) {
        clearInterval(this._timer);
        this._timer = undefined;
      }
    };
  }

  /** Pide una vuelta ya, sin esperar al intervalo. Para después de tocar un
   *  botón: si no, el botón se queda con la etiqueta vieja hasta 400 ms. */
  refrescar() { this._tick(); }

  private async _tick() {
    if (this._enVuelo) return;
    this._enVuelo = true;
    try {
      const [audio, llm] = await Promise.all([this._svc.audio(), this._svc.llm()]);
      this.ultima = { audio, llm };
      this._oyentes.forEach(fn => fn(this.ultima));
    } catch {
      /* el servidor está reiniciando; la próxima vuelta lo agarra */
    } finally {
      this._enVuelo = false;
    }
  }
}

export const audioStore = new AudioStore();
