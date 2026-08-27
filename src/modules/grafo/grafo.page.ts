import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { SistemaService } from '../sistema/sistema.service';
import { GrafoService, EstadoGrafo } from './grafo.service';
import './grafo-vivo';

/** La vista completa: el mismo grafo que se ve en `/russ`, mas la historia y
 *  el único control que hay que entender antes de tocarlo. */
@customElement('grafo-page')
export class GrafoPage extends LitElement {
  private _svc = new GrafoService();
  private _sistema = new SistemaService();

  @state() private _g: EstadoGrafo | null = null;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._leer();
  }

  disconnectedCallback() {
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _leer() {
    this._svc.estado().then(g => { this._g = g; }).catch(() => {});
  }

  private async _toggle() {
    await this._sistema.toggle('iniciativa', !this._g?.iniciativa);
    this._leer();
  }

  /** La iniciativa es el único interruptor de toda la app que cambia lo que
   *  Russ HACE y no lo que se ve. Por eso se explica antes de ofrecerlo: el
   *  botón que decía sólo «prender iniciativa» no le decía nada a nadie. */
  private _renderIniciativa(): TemplateResult {
    const g = this._g;
    const on = !!g?.iniciativa;
    return html`
      <section class="bg-white border rounded-[var(--radius-surface)] p-4 shadow-sm
                      ${on ? 'border-amber-300' : 'border-gray-200'}">
        <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('grafo.pregunta')}</h3>
        <p class="text-sm text-[var(--neutral-600)] mb-3">
          ${on ? t('grafo.iniciativa_on') : t('grafo.iniciativa_off')}
        </p>
        <p class="text-xs text-[var(--neutral-500)] mb-3 leading-relaxed">${t('grafo.explicacion')}</p>
        <div class="flex items-center gap-3 flex-wrap">
          <button @click="${() => this._toggle()}"
            class="px-4 py-2 text-sm font-medium rounded-[var(--radius-control)] border transition-colors
                   ${on ? 'bg-amber-600 border-amber-600 text-white hover:bg-amber-700'
                        : 'bg-white border-gray-200 hover:border-[var(--color-accent)]'}">
            ${on ? t('grafo.apagar') : t('grafo.prender')}
          </button>
          ${g && g.cooldown_restante_s > 0
            ? html`<span class="text-xs text-amber-700 bg-amber-50 border border-amber-200
                                px-2.5 py-1 rounded-full tabular-nums">
                     ${t('grafo.cooldown', { s: g.cooldown_restante_s })}
                   </span>` : ''}
          ${g?.ultimo_motivo
            ? html`<span class="text-xs text-[var(--neutral-500)]">
                     ${t('grafo.ultimo_motivo', { m: g.ultimo_motivo })}
                   </span>` : ''}
        </div>
      </section>`;
  }

  render(): TemplateResult {
    return html`
      <h2 class="text-2xl font-semibold text-gray-900 mb-5">${t('grafo.title')}</h2>
      <div class="flex flex-col gap-4 max-w-3xl">
        <grafo-vivo></grafo-vivo>
        ${this._renderIniciativa()}
      </div>`;
  }
}
