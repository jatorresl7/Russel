import { html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { CrudTable } from '../../crud/crud-table';
import { Carga } from '../../crud/carga';
import { t } from '../../i18n/t';
import { ConocimientoService, Memoria } from './conocimiento.service';

@customElement('conocimiento-table')
export class ConocimientoTable extends CrudTable<Memoria> {
  get prefix() { return 'conocimiento'; }
  service = new ConocimientoService();

  // El backend pagina y filtra: pueden llegar a ser miles de memorias y no
  // tiene sentido bajarlas todas para mostrar cincuenta.
  protected get serverPaginated() { return true; }
  protected searchTerm() { return this._busqueda; }

  @state() private _busqueda = '';

  private _buscar(v: string) {
    this._busqueda = v;
    this.reloadPage(true);
  }

  protected renderToolbar(): TemplateResult {
    return html`
      <div class="mb-3">
        <input .value="${this._busqueda}"
          @input="${(e: Event) => this._buscar((e.target as HTMLInputElement).value)}"
          placeholder="${t('conocimiento.texto')}…"
          class="w-full max-w-sm px-3 py-2 text-sm rounded-[var(--radius-control)]
                 border border-gray-300 focus:outline-none focus:border-[var(--color-accent)]" />
      </div>`;
  }

  private async _aprobar(m: Memoria) {
    await this.service.aprobar(m.id, !m.vigente);
    Carga.invalidar('conocimiento');
    this.reloadPage();
  }

  /** La vigencia es el estado Y el interruptor: lo que sale de la
   *  consolidacion nace en espera, y aprobarlo es un clic sobre la misma
   *  pastilla que dice que esta esperando. */
  private _vigencia(m: Memoria): TemplateResult {
    return html`
      <button @click="${() => this._aprobar(m)}"
        title="${t(m.vigente ? 'conocimiento.quitar' : 'conocimiento.aprobar')}"
        class="px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors
               ${m.vigente ? 'bg-green-50 border-green-200 text-green-700 hover:bg-green-100'
                           : 'bg-amber-50 border-amber-300 text-amber-800 hover:bg-amber-100'}">
        ${t(m.vigente ? 'conocimiento.usando' : 'conocimiento.esperando')}
      </button>`;
  }

  private _pastilla(texto: string, clases: string): TemplateResult {
    return html`<span class="px-2 py-0.5 rounded-full text-[11px] font-medium ${clases}">${texto}</span>`;
  }

  columns = () => [
    { key: 'texto', label: t('conocimiento.texto') },
    { key: 'tipo', label: t('conocimiento.tipo'),
      renderer: (m: Memoria) => this._pastilla(
        t(`conocimiento.${m.tipo}`),
        m.tipo === 'hecho' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700') },
    { key: 'fuente', label: t('conocimiento.fuente'),
      renderer: (m: Memoria) => this._pastilla(
        t(`conocimiento.${m.fuente}`),
        m.fuente === 'explicito' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600') },
    { key: 'vigente', label: t('conocimiento.estado'),
      renderer: (m: Memoria) => this._vigencia(m) },
    { key: 'usos', label: t('conocimiento.usos') },
  ];
}
