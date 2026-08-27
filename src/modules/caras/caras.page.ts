import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Carga } from '../../crud/carga';
import { t, subscribeI18n } from '../../i18n/t';
import { CarasService, EstadoCaras } from './caras.service';
import '../vision/camara-panel';

/** El estado se refresca solo porque «viendo ahora» es en vivo: cambia con
 *  quien se para delante de la cámara. */
const MS_SONDEO = 2000;

@customElement('caras-page')
export class CarasPage extends LitElement {
  private _svc = new CarasService();
  private _datos = new Carga<EstadoCaras | null>(this, null);

  /** nombre -> archivos de sus recortes. Se pide aparte del estado porque casi
   *  nunca cambia; solo se recarga al enrolar o al olvidar. */
  @state() private _fotos: Record<string, string[]> = {};
  @state() private _nombre = '';
  @state() private _cantidad = 5;
  @state() private _enrolando = false;
  @state() private _aviso = '';

  private _sondeo?: number;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._cargar().then(() => this._cargarFotos());
    this._sondeo = window.setInterval(() => this._cargar(), MS_SONDEO);
  }

  disconnectedCallback() {
    clearInterval(this._sondeo);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _cargar() {
    // Sin clave de caché: «viendo ahora» es estado en vivo, servir lo guardado
    // mostraría a alguien que ya se fue de cuadro.
    return this._datos.pedir(() => this._svc.estado());
  }

  private async _cargarFotos() {
    const nombres = Object.keys(this._datos.valor?.conocidos ?? {});
    const pares = await Promise.all(
      nombres.map(async n => [n, await this._svc.fotos(n).catch(() => [])] as const));
    this._fotos = Object.fromEntries(pares);
  }

  private async _enrolar() {
    const nombre = this._nombre.trim();
    if (!nombre) return;
    this._enrolando = true;
    this._aviso = '';
    try {
      const r = await this._svc.enrolar(nombre, this._cantidad);
      this._aviso = r.fallos?.length ? r.fallos.join(' · ') : `${r.guardadas ?? 0} / ${this._cantidad}`;
      this._nombre = '';
      await this._cargar();
      await this._cargarFotos();
    } finally {
      this._enrolando = false;
    }
  }

  private async _olvidar(nombre: string) {
    await this._svc.olvidar(nombre);
    await this._cargar();
    await this._cargarFotos();
  }

  private _renderPersona(nombre: string, vectores: number): TemplateResult {
    const fotos = this._fotos[nombre] ?? [];
    return html`
      <div class="mb-5">
        <div class="flex items-baseline gap-2.5 mb-2">
          <h4 class="text-sm font-semibold text-gray-900">${nombre}</h4>
          <span class="text-xs text-[var(--neutral-500)]">${t('caras.vectors', { n: vectores })}</span>
          <button @click="${() => this._olvidar(nombre)}"
            class="ml-auto text-xs text-red-500 hover:text-red-700 bg-transparent border-0 px-1">
            ${t('caras.forget')}
          </button>
        </div>
        ${fotos.length
          ? html`<div class="flex gap-2 flex-wrap">
                   ${fotos.map(f => html`
                     <img src="${CarasService.foto(nombre, f)}" title="${f}" alt="${nombre}"
                       class="w-28 h-28 object-cover rounded-[var(--radius-control)] border border-gray-200" />`)}
                 </div>`
          : html`<p class="text-xs italic text-[var(--neutral-500)]">${t('caras.no_crops')}</p>`}
      </div>`;
  }

  private _renderEnrolar(): TemplateResult {
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-2">
          ${t('caras.enroll')}
        </h3>
        <p class="text-xs text-[var(--neutral-600)] mb-3 leading-snug">${t('caras.enroll_hint')}</p>
        <div class="flex gap-2 flex-wrap items-center">
          <input .value="${this._nombre}"
            @input="${(e: Event) => { this._nombre = (e.target as HTMLInputElement).value; }}"
            @keydown="${(e: KeyboardEvent) => { if (e.key === 'Enter') this._enrolar(); }}"
            placeholder="${t('caras.name_placeholder')}"
            class="flex-1 min-w-[140px] px-3 py-2 text-sm rounded-[var(--radius-control)]
                   border border-gray-300 focus:outline-none focus:border-[var(--color-accent)]" />
          <input type="number" min="1" max="20" .value="${String(this._cantidad)}"
            @input="${(e: Event) => { this._cantidad = Number((e.target as HTMLInputElement).value) || 5; }}"
            title="${t('caras.photos')}"
            class="w-20 px-3 py-2 text-sm rounded-[var(--radius-control)]
                   border border-gray-300 focus:outline-none focus:border-[var(--color-accent)]" />
          <button @click="${() => this._enrolar()}" ?disabled="${this._enrolando || !this._nombre.trim()}"
            class="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-[var(--radius-control)]
                   text-sm font-medium transition-colors disabled:opacity-50">
            ${this._enrolando ? t('caras.enrolling') : t('caras.enroll')}
          </button>
        </div>
        ${this._aviso ? html`<p class="mt-2.5 text-xs text-[var(--neutral-600)]">${this._aviso}</p>` : ''}
      </section>`;
  }

  render(): TemplateResult {
    const e = this._datos.valor;
    const conocidos = Object.entries(e?.conocidos ?? {});
    const tracks = Object.entries(e?.tracks ?? {});

    return html`
      <h2 class="text-2xl font-semibold text-gray-900 mb-5">${t('caras.title')}</h2>

      <div class="grid gap-4 lg:grid-cols-[1fr_360px] max-w-5xl">
        <div class="flex flex-col gap-4">
          ${this._renderEnrolar()}

          <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-3">
              ${t('caras.enrolled')}
            </h3>
            <div class="carga-contenido">
              ${conocidos.length
                ? conocidos.map(([n, v]) => this._renderPersona(n, v))
                : html`<p class="text-sm text-[var(--neutral-500)] py-4">${t('caras.empty')}</p>`}
            </div>
          </section>

          <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-3">
              ${t('caras.watching')}
              <span class="normal-case font-normal tracking-normal">
                · ${t('caras.threshold', { v: e?.umbral ?? '—' })}
              </span>
            </h3>
            <ul class="list-none p-0 carga-contenido">
              ${tracks.length
                ? tracks.map(([id, tr]) => html`
                    <li class="flex items-baseline gap-2 py-1.5 border-b border-gray-50 last:border-0 text-sm">
                      <span class="text-[var(--neutral-500)]">track #${id}</span>
                      <b class="text-gray-900">${tr.nombre ?? t('caras.unknown')}</b>
                      <code class="ml-auto text-xs text-green-600 tabular-nums">${tr.score}</code>
                    </li>`)
                : html`<li class="text-sm italic text-[var(--neutral-500)] py-1.5">${t('caras.nobody')}</li>`}
            </ul>
          </section>
        </div>

        <camara-panel></camara-panel>
      </div>`;
  }
}
