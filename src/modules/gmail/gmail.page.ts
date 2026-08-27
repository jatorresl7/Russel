import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Carga } from '../../crud/carga';
import { t, subscribeI18n } from '../../i18n/t';
import { GmailService, ResumenGmail } from './gmail.service';

@customElement('gmail-page')
export class GmailPage extends LitElement {
  private _svc = new GmailService();
  private _datos = new Carga<ResumenGmail[]>(this, []);
  @state() private _resumiendo = false;

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._cargar();
  }

  disconnectedCallback() {
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _cargar() {
    return this._datos.pedir(() => this._svc.listar(), 'gmail-summaries');
  }

  private async _resumir() {
    this._resumiendo = true;
    try {
      await this._svc.resumirHoy();
      Carga.invalidar('gmail');   // acaba de aparecer un resumen nuevo
      await this._cargar();
    } finally {
      this._resumiendo = false;
    }
  }

  private _tarjeta(r: ResumenGmail): TemplateResult {
    return html`
      <article class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
        <header class="flex items-center gap-2.5 mb-3">
          <span class="text-sm font-semibold text-gray-900">${r.date}</span>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-[11px] text-gray-600">
            ${t('gmail.emails', { count: r.email_count })}
          </span>
        </header>
        <p class="text-sm text-gray-700 whitespace-pre-wrap break-words">${r.summary}</p>
      </article>`;
  }

  render(): TemplateResult {
    return html`
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-2xl font-semibold text-gray-900">${t('gmail.title')}</h2>
        <button @click="${() => this._resumir()}" ?disabled="${this._resumiendo}"
          class="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-[var(--radius-control)]
                 text-sm font-medium transition-colors disabled:opacity-50">
          ${this._resumiendo ? t('gmail.summarizing') : t('gmail.summarize')}
        </button>
      </div>

      <div class="carga-contenido flex flex-col gap-3">
        ${this._datos.error
          ? html`<p class="py-10 text-center text-red-400 bg-white rounded-[var(--radius-surface)] shadow-sm">${t('common.error_loading')}</p>`
          : this._datos.vacia
          ? html`<p class="py-10 text-center text-[var(--neutral-500)] bg-white rounded-[var(--radius-surface)] shadow-sm">${t('common.loading')}</p>`
          : this._datos.valor.length
          ? this._datos.valor.map(r => this._tarjeta(r))
          : html`<p class="py-10 text-center text-[var(--neutral-500)] bg-white rounded-[var(--radius-surface)] shadow-sm">${t('gmail.empty')}</p>`}
      </div>`;
  }
}
