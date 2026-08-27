import { html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { CrudPage } from '../../crud/crud-page';
import { Carga } from '../../crud/carga';
import { t } from '../../i18n/t';
import { SistemaService } from '../sistema/sistema.service';
import { ConocimientoService, Memoria, EstadoMemoria, Recuperada } from './conocimiento.service';
import { ConocimientoTable } from './conocimiento.table';
import { ConocimientoForm } from './conocimiento.form';

@customElement('conocimiento-page')
export class ConocimientoPage extends CrudPage<Memoria> {
  get prefix() { return 'conocimiento'; }
  get label()  { return t('conocimiento.title'); }
  createTable = () => new ConocimientoTable();
  createForm  = () => new ConocimientoForm();

  private _svc = new ConocimientoService();
  private _sistema = new SistemaService();

  @state() private _est: EstadoMemoria | null = null;
  @state() private _consultando = '';
  @state() private _recuperadas: Recuperada[] | null = null;
  @state() private _consolidando = false;
  @state() private _aviso = '';

  connectedCallback() {
    super.connectedCallback();
    this._leerEstado();
  }

  private _leerEstado() {
    this._svc.estado().then(e => { this._est = e; }).catch(() => {});
  }

  private async _consolidar() {
    this._consolidando = true;
    try {
      const r = await this._svc.consolidar();
      this._aviso = `${r.leidos} → ${r.guardadas}`;
      Carga.invalidar('conocimiento');
      this._leerEstado();
    } finally {
      this._consolidando = false;
    }
  }

  private async _probar() {
    if (!this._consultando.trim()) { this._recuperadas = null; return; }
    this._recuperadas = await this._svc.probar(this._consultando).catch(() => []);
  }

  private async _prenderEmbed() {
    await this._sistema.toggle('embed', true);
    this._leerEstado();
  }

  private _dato(n: number | string, etiqueta: string): TemplateResult {
    return html`
      <div class="bg-white border border-gray-200 rounded-[var(--radius-surface)] px-3.5 py-2.5">
        <div class="text-lg font-semibold tabular-nums text-gray-900">${n}</div>
        <div class="text-[11px] text-[var(--neutral-500)]">${etiqueta}</div>
      </div>`;
  }

  private _renderCabecera(): TemplateResult {
    const e = this._est;
    if (!e) return html``;
    return html`
      ${e.embed && !e.embed.activo ? html`
        <div class="mb-4 rounded-[var(--radius-control)] bg-amber-50 border border-amber-200 px-3.5 py-3">
          <p class="text-xs text-amber-900 mb-2">${t('conocimiento.embed_off')}</p>
          <button @click="${() => this._prenderEmbed()}"
            class="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-control)]
                   bg-amber-600 hover:bg-amber-700 text-white border-0 transition-colors">
            ${t('conocimiento.embed_on')}
          </button>
        </div>` : ''}

      <div class="grid gap-2.5 grid-cols-2 sm:grid-cols-4 mb-4">
        ${this._dato(e.total ?? 0, t('conocimiento.total', { n: e.total ?? 0 }))}
        ${this._dato(e.por_fuente?.explicito ?? 0, t('conocimiento.explicito'))}
        ${this._dato(e.por_fuente?.consolidado ?? 0, t('conocimiento.consolidado'))}
        ${this._dato(e.esperando ?? 0, t('conocimiento.en_espera', { n: e.esperando ?? 0 }))}
      </div>

      ${e.esperando
        ? html`<p class="mb-4 px-3.5 py-2.5 rounded-[var(--radius-control)] bg-amber-50
                         border border-amber-200 text-xs text-amber-900 leading-relaxed">
                 ${t('conocimiento.aviso_consolidado')}
               </p>` : ''}`;
  }

  /** Ver qué recuperaría Russ para una frase, sin gastarle un turno. Es la
   *  única forma honesta de ajustar el umbral: los números de similitud de e5
   *  están todos apretados arriba y no se pueden intuir. */
  private _renderProbar(): TemplateResult {
    const u = this._est?.umbral ?? 0;
    return html`
      <section class="mt-6 bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-3">
          ${t('conocimiento.probar')}
        </h3>
        <div class="flex gap-2 flex-wrap">
          <input .value="${this._consultando}"
            @input="${(e: Event) => { this._consultando = (e.target as HTMLInputElement).value; }}"
            @keydown="${(e: KeyboardEvent) => { if (e.key === 'Enter') this._probar(); }}"
            placeholder="${t('conocimiento.probar_ph')}"
            class="flex-1 min-w-[220px] px-3 py-2 text-sm rounded-[var(--radius-control)]
                   border border-gray-300 focus:outline-none focus:border-[var(--color-accent)]" />
          <button @click="${() => this._probar()}"
            class="bg-primary hover:bg-primary-hover text-white px-4 py-2
                   rounded-[var(--radius-control)] text-sm font-medium transition-colors">
            ${t('conocimiento.probar')}
          </button>
        </div>
        ${this._recuperadas === null ? '' : this._recuperadas.length
          ? html`
            <ul class="list-none p-0 mt-3 flex flex-col gap-1.5">
              ${this._recuperadas.map(r => html`
                <li class="flex items-baseline gap-3 text-sm border-l-2 border-[var(--color-accent)] pl-2.5">
                  <span class="flex-1 text-gray-800">${r.texto}</span>
                  <code class="text-xs text-[var(--color-accent)] tabular-nums">${r.sim}</code>
                </li>`)}
            </ul>`
          : html`<p class="mt-3 text-sm text-[var(--neutral-500)]">
                   ${t('conocimiento.sin_resultados', { u })}
                 </p>`}
      </section>`;
  }

  render(): TemplateResult {
    return html`
      ${this._renderCabecera()}
      ${super.render()}

      <div class="flex items-center gap-2.5 mt-5 flex-wrap">
        <button @click="${() => this._consolidar()}" ?disabled="${this._consolidando}"
          class="px-4 py-2 text-sm rounded-[var(--radius-control)] border border-gray-200
                 bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-50">
          ${this._consolidando ? t('conocimiento.consolidando') : t('conocimiento.consolidar')}
        </button>
        ${this._aviso ? html`<span class="text-sm text-[var(--neutral-600)]">${this._aviso}</span>` : ''}
      </div>

      ${this._renderProbar()}`;
  }
}
