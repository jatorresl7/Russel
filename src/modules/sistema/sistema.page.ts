import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Carga } from '../../crud/carga';
import { t, subscribeI18n } from '../../i18n/t';
import { SistemaService, EstadoSistema, EstadoLlm } from './sistema.service';

/** El LLM tarda en cargar y su velocidad cambia turno a turno, así que esta
 *  vista se refresca sola mientras está abierta. Más lento que la consola
 *  (400 ms) porque acá no hay nada que siga el pulso de la voz. */
const MS_SONDEO = 2000;

@customElement('sistema-page')
export class SistemaPage extends LitElement {
  private _svc = new SistemaService();
  private _sistema = new Carga<EstadoSistema | null>(this, null);
  private _llm = new Carga<EstadoLlm | null>(this, null);
  @state() private _ocupado = false;

  private _sondeo?: number;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._cargar();
    this._sondeo = window.setInterval(() => this._cargar(), MS_SONDEO);
  }

  disconnectedCallback() {
    clearInterval(this._sondeo);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _cargar() {
    // Sin clave de caché a propósito: es estado en vivo, servir lo guardado
    // mostraría hilos y tok/s de hace un rato como si fueran los de ahora.
    this._sistema.pedir(() => this._svc.estado());
    this._llm.pedir(() => this._svc.llm());
  }

  private async _toggle(modulo: string, on: boolean) {
    this._ocupado = true;
    try {
      this._sistema.set(await this._svc.toggle(modulo, on));
      await this._llm.pedir(() => this._svc.llm());
    } finally {
      this._ocupado = false;
    }
  }

  private async _llmRam(cargar: boolean) {
    this._ocupado = true;
    try {
      this._llm.set(cargar ? await this._svc.cargarLlm() : await this._svc.descargarLlm());
    } finally {
      this._ocupado = false;
    }
  }

  private _dato(label: string, valor: unknown): TemplateResult {
    return html`
      <div class="flex items-baseline justify-between gap-4 py-2 border-b border-gray-50 last:border-0">
        <span class="text-sm text-[var(--neutral-600)]">${label}</span>
        <span class="text-sm font-medium text-gray-900 text-right break-all">${valor}</span>
      </div>`;
  }

  private _renderModulos(s: EstadoSistema): TemplateResult {
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
        <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('sistema.cpu_budget')}</h3>
        <p class="text-xs text-[var(--neutral-500)] mb-4">
          ${s.device} · ${s.compute_type} · ${t('sistema.threads', { n: s.total_hilos })}
        </p>
        <div class="flex flex-col gap-2">
          ${Object.entries(s.modulos).map(([nombre, m]) => html`
            <div class="flex items-center gap-3 py-1.5">
              <button @click="${() => this._toggle(nombre, !m.activo)}" ?disabled="${this._ocupado}"
                class="w-11 h-6 rounded-full relative transition-colors flex-shrink-0 border-0
                       disabled:opacity-40 ${m.activo ? 'bg-green-500' : 'bg-gray-300'}"
                title="${m.activo ? t('sistema.on') : t('sistema.off')}">
                <span class="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-[left]
                             ${m.activo ? 'left-[22px]' : 'left-0.5'}"></span>
              </button>
              <span class="text-sm font-medium text-gray-900 flex-1">${nombre}</span>
              <span class="text-xs text-[var(--neutral-500)]">
                ${m.activo ? t('sistema.threads', { n: m.hilos }) : t('sistema.off')}
              </span>
            </div>`)}
        </div>
      </section>`;
  }

  private _renderLlm(l: EstadoLlm): TemplateResult {
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
        <h3 class="text-sm font-semibold text-gray-900 mb-3">${t('sistema.llm_status')}</h3>
        ${this._dato(t('sistema.model'),  l.modelo)}
        ${this._dato(t('sistema.engine'), l.motor)}
        ${this._dato(t('sistema.loaded'), l.cargado ? t('common.yes') : t('common.no'))}
        ${this._dato(t('sistema.speed'),  `${l.tok_s} tok/s`)}
        ${this._dato(t('sistema.prefill'), `${l.prefill_ms} ms`)}
        ${this._dato(t('sistema.turns'),  l.turnos)}
        ${l.error ? html`<p class="mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded-[var(--radius-control)] text-xs text-red-700">${l.error}</p>` : ''}
        <div class="flex gap-2 mt-4">
          <button @click="${() => this._llmRam(true)}" ?disabled="${this._ocupado || l.cargado}"
            class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                   bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
            ${t('sistema.load')}
          </button>
          <button @click="${() => this._llmRam(false)}" ?disabled="${this._ocupado || !l.cargado}"
            class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                   bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
            ${t('sistema.unload')}
          </button>
        </div>
      </section>`;
  }

  render(): TemplateResult {
    const s = this._sistema.valor;
    const l = this._llm.valor;

    return html`
      <h2 class="text-2xl font-semibold text-gray-900 mb-5">${t('sistema.title')}</h2>
      <div class="carga-contenido grid gap-5 md:grid-cols-2 max-w-4xl">
        ${s ? this._renderModulos(s)
            : html`<p class="py-10 text-center text-[var(--neutral-500)] bg-white rounded-[var(--radius-surface)] shadow-sm">
                     ${this._sistema.error ? t('common.error_loading') : t('common.loading')}
                   </p>`}
        ${l ? this._renderLlm(l) : ''}
      </div>`;
  }
}
