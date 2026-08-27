import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { EstadoAudio, VACIO } from './audio.service';
import { audioStore } from './audio.store';
import { SistemaService } from '../sistema/sistema.service';

/**
 * Lo que el micrófono está oyendo, mientras lo oye.
 *
 * Es la prueba de vida del audio. La pastilla de estado dice «escuchando», pero
 * eso lo dice igual con el micrófono mudo; ver aparecer tus propias palabras es
 * lo único que confirma que la cadena entera —driver, VAD, vosk, whisper— está
 * funcionando.
 *
 * Se muestran las dos capas porque dicen cosas distintas:
 *  - vosk sale al instante y con errores. Sirve para saber QUE te oye.
 *  - LocalAgreement confirma palabras cuando dos pasadas de whisper coinciden.
 *    Lo confirmado ya no cambia; lo pendiente todavía puede.
 *
 * Las dos dependen del módulo `asr_stream`, que viene APAGADO por defecto. Con
 * él apagado no aparece nada mientras hablás — la frase sale entera recién
 * cuando terminás y corre la pasada final. Eso es indistinguible de un
 * micrófono roto, así que el panel lo dice y ofrece prenderlo.
 */
@customElement('escucha-viva')
export class EscuchaViva extends LitElement {
  @state() private _a: EstadoAudio = VACIO;
  @state() private _enVivo = true;

  private _sistema = new SistemaService();
  private _unsub?: () => void;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = audioStore.suscribir(i => { this._a = i.audio; });
    this._leerModulo();
  }

  private _leerModulo() {
    this._sistema.estado()
      .then(s => { this._enVivo = !!s.modulos['asr_stream']?.activo; })
      .catch(() => {});
  }

  private async _prenderEnVivo() {
    await this._sistema.toggle('asr_stream', true);
    this._enVivo = true;
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _etiqueta(texto: string): TemplateResult {
    return html`<div class="text-[10.5px] uppercase tracking-wider text-[var(--neutral-500)] mb-1">${texto}</div>`;
  }

  private _renderVivo(): TemplateResult {
    const a = this._a;
    return html`
      <div class="rounded-[var(--radius-control)] bg-[var(--neutral-050)]
                  border border-gray-200 px-3.5 py-3 mb-3
                  ${a.transcribiendo ? 'latiendo' : ''}">
        ${this._etiqueta(t('escucha.confirmed'))}
        <p class="text-sm text-gray-900 break-words min-h-[1.4em]">
          <span>${a.committed}${a.committed ? ' ' : ''}</span
          ><span class="opacity-45 italic">${a.pending}</span>
        </p>
        ${a.vosk ? html`
          <div class="mt-2.5 pt-2.5 border-t border-gray-200">
            ${this._etiqueta(t('escucha.instant'))}
            <p class="text-sm text-[var(--neutral-600)] break-words">${a.vosk}</p>
          </div>` : ''}
      </div>`;
  }

  private _renderApagado(): TemplateResult {
    return html`
      <div class="rounded-[var(--radius-control)] bg-amber-50 border border-amber-200
                  px-3.5 py-3 mb-3">
        <p class="text-xs text-amber-900 mb-2 leading-snug">${t('escucha.stream_off')}</p>
        <button @click="${() => this._prenderEnVivo()}"
          class="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-control)]
                 bg-amber-600 hover:bg-amber-700 text-white border-0 transition-colors">
          ${t('escucha.stream_on')}
        </button>
        <span class="text-[11px] text-amber-800/70 ml-2">${t('escucha.stream_cost')}</span>
      </div>`;
  }

  render(): TemplateResult {
    const a = this._a;
    const hayVivo = !!(a.committed || a.pending || a.vosk);

    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)]
                      p-4 shadow-sm flex flex-col min-h-0 h-full">
        <div class="flex items-baseline gap-2 mb-3 flex-shrink-0">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)]">
            ${t('escucha.title')}
          </h3>
          ${a.pasadas ? html`
            <span class="text-[11px] text-[var(--neutral-500)] tabular-nums ml-auto">
              ${t('consola.passes', { n: a.pasadas, ms: a.ultima_pasada_ms })}
            </span>` : ''}
        </div>

        ${this._enVivo ? '' : this._renderApagado()}
        ${hayVivo ? this._renderVivo() : ''}

        ${a.transcripts.length
          ? html`
              ${this._etiqueta(t('escucha.recent'))}
              <ul class="list-none p-0 flex flex-col gap-1.5 flex-1 min-h-0 overflow-y-auto">
                ${a.transcripts.map(tr => html`
                  <li class="border-l-2 border-[var(--color-accent)] pl-2.5 py-0.5">
                    <div class="text-[10.5px] text-[var(--neutral-500)] tabular-nums">
                      ${tr.at} · ${tr.dur}s · whisper ${tr.took}s
                    </div>
                    <p class="text-sm text-gray-800 break-words">${tr.text}</p>
                  </li>`)}
              </ul>`
          : hayVivo ? ''
          : html`<p class="text-sm text-[var(--neutral-500)] py-2">
                   ${a.listening ? t('escucha.nothing') : t('escucha.mic_off')}
                 </p>`}
      </section>`;
  }
}
