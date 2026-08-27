import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { AudioService, EstadoAudio, EstadoLlmBarra, VACIO } from './audio.service';
import { audioStore } from './audio.store';

type Tono = 'off' | 'on' | 'busy' | 'bad';

/**
 * Estado del micrófono y del LLM, con los tres botones que los manejan.
 *
 * La pastilla del micrófono tiene cinco estados y no dos. Los dos que faltaban
 * son justamente los que tardan: cargar los modelos y la pasada final de
 * whisper. Mientras corrían, la pantalla se quedaba igual con la máquina al
 * máximo — y desde afuera eso es idéntico a un micrófono que no anda.
 */
@customElement('estado-barra')
export class EstadoBarra extends LitElement {
  private _svc = new AudioService();

  @state() private _audio: EstadoAudio = VACIO;
  @state() private _llm: EstadoLlmBarra =
    { activo: false, cargado: false, generando: false, modelo: '', tok_s: 0 };

  private _unsub?: () => void;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = audioStore.suscribir(i => { this._audio = i.audio; this._llm = i.llm; });
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _accion(path: string, body?: unknown) {
    this._svc.post(path, body).catch(() => {}).finally(() => audioStore.refrescar());
  }

  /** Qué está pasando con el micrófono, en orden de importancia: primero lo
   *  que tarda, después lo que está pasando ahora. */
  private _micro(): { texto: string; tono: Tono; latiendo: boolean } {
    const a = this._audio;
    if (a.cargando)       return { texto: t('consola.loading_models'), tono: 'busy', latiendo: true };
    if (a.transcribiendo) return { texto: t('consola.analyzing'),      tono: 'busy', latiendo: true };
    if (a.speaking)       return { texto: t('consola.speaking'),       tono: 'on',   latiendo: false };
    if (a.listening)      return { texto: t('consola.listening'),      tono: 'on',   latiendo: false };
    return { texto: t('consola.mic'), tono: 'off', latiendo: false };
  }

  private _pastilla(texto: string, tono: Tono, latiendo = false): TemplateResult {
    const tonos: Record<Tono, string> = {
      off:  'text-gray-500 border-gray-200 bg-white',
      on:   'text-green-700 border-green-200 bg-green-50',
      busy: 'text-amber-800 border-amber-300 bg-amber-50 font-medium',
      bad:  'text-red-700 border-red-200 bg-red-50',
    };
    return html`<span class="text-xs px-2.5 py-1 rounded-full border whitespace-nowrap
                             ${tonos[tono]} ${latiendo ? 'latiendo' : ''}">${texto}</span>`;
  }

  private _boton(texto: string, onClick: () => void): TemplateResult {
    return html`
      <button @click="${onClick}"
        class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
               bg-white hover:border-[var(--color-accent)] transition-colors">
        ${texto}
      </button>`;
  }

  render(): TemplateResult {
    const a = this._audio, l = this._llm;
    const micro = this._micro();
    const llmTexto = l.generando ? t('consola.generating')
      : (l.cargado ? (l.modelo?.split('/').pop() ?? l.modelo) : t('consola.llm_idle'));

    return html`
      <div class="flex items-center gap-2.5 flex-wrap">
        ${this._pastilla(micro.texto, micro.tono, micro.latiendo)}

        <!-- Nivel de voz: sale directo de la probabilidad del VAD -->
        <div class="w-[70px] h-1.5 rounded bg-gray-200 overflow-hidden" title="VAD">
          <div class="h-full bg-green-500 transition-[width] duration-100"
               style="width:${Math.round((a.vad || 0) * 100)}%"></div>
        </div>

        ${a.buffer_s ? this._pastilla(t('consola.buffer', { s: a.buffer_s.toFixed(1) }), 'off') : ''}
        ${a.dropped  ? this._pastilla(t('consola.dropped', { n: a.dropped }), 'bad') : ''}
        ${a.error    ? this._pastilla(a.error, 'bad') : ''}

        ${this._pastilla(llmTexto, l.generando ? 'busy' : (l.cargado ? 'on' : 'off'), l.generando)}
        ${l.tok_s ? this._pastilla(`${l.tok_s} tok/s`, 'off') : ''}

        <span class="flex-1"></span>

        ${this._boton(a.listening ? t('consola.stop_listening') : t('consola.listen'),
                      () => this._accion(a.listening ? 'audio/stop' : 'audio/start'))}
        ${this._boton(l.activo ? t('consola.llm_off') : t('consola.llm_on'),
                      () => this._accion('system/toggle', { modulo: 'llm', on: !l.activo }))}
        ${this._boton(t('consola.clear'), () => this._accion('assistant/clear'))}
      </div>`;
  }
}
