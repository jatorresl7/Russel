import { html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { CrudPage } from '../../crud/crud-page';
import { t } from '../../i18n/t';
import { ScriptsService, WorkScript } from './scripts.service';
import { ScriptsTable } from './scripts.table';
import { ScriptsForm } from './scripts.form';

@customElement('scripts-page')
export class ScriptsPage extends CrudPage<WorkScript> {
  get prefix() { return 'scripts'; }
  get label()  { return t('scripts.title'); }
  createTable = () => new ScriptsTable();
  createForm  = () => new ScriptsForm();

  private _svc = new ScriptsService();
  @state() private _aviso = '';

  private async _generar() {
    const r = await this._svc.generate();
    this._aviso = t('scripts.generated', { scripts: r.scripts_included.join(', ') || '—' });
  }

  private async _correr() {
    await this._svc.run();
    this._aviso = t('scripts.launched');
  }

  /** El listado es el CRUD de siempre; debajo van las dos acciones que no son
   *  sobre UNA fila sino sobre el conjunto: regenerar launch.sh y lanzarlo. */
  render(): TemplateResult {
    return html`
      ${super.render()}
      <div class="flex items-center gap-2.5 mt-5 flex-wrap">
        <button @click="${() => this._generar()}"
          class="px-4 py-2 text-sm rounded-[var(--radius-control)] border border-gray-200
                 bg-white hover:border-[var(--color-accent)] transition-colors">
          ${t('scripts.generate')}
        </button>
        <button @click="${() => this._correr()}"
          class="px-4 py-2 text-sm rounded-[var(--radius-control)] border border-gray-200
                 bg-white hover:border-[var(--color-accent)] transition-colors">
          ${t('scripts.run')}
        </button>
        ${this._aviso ? html`<span class="text-sm text-[var(--neutral-600)]">${this._aviso}</span>` : ''}
      </div>`;
  }
}
