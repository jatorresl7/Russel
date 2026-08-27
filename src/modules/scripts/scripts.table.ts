import { html, TemplateResult } from 'lit';
import { customElement } from 'lit/decorators.js';
import { CrudTable } from '../../crud/crud-table';
import { Carga } from '../../crud/carga';
import { t } from '../../i18n/t';
import { ScriptsService, WorkScript } from './scripts.service';

@customElement('scripts-table')
export class ScriptsTable extends CrudTable<WorkScript> {
  get prefix() { return 'scripts'; }
  service = new ScriptsService();

  // El backend solo tiene GET, POST y el toggle: sin PUT ni DELETE no hay nada
  // detrás de esos botones, así que no se pintan.
  canEdit = false;
  canDelete = false;

  private async _toggle(s: WorkScript) {
    await this.service.toggle(s.id);
    Carga.invalidar('scripts');   // obligatorio tras mutar, o vuelve el estado viejo
    this.reloadPage();
  }

  /** La columna «habilitado» es el propio interruptor: el estado y la acción
   *  son la misma cosa, y un botón aparte para dos valores sobra. */
  private _interruptor(s: WorkScript): TemplateResult {
    return html`
      <button @click="${() => this._toggle(s)}"
        class="px-2.5 py-1 rounded-full text-xs font-medium border transition-colors
               ${s.enabled ? 'bg-green-50 border-green-200 text-green-700 hover:bg-green-100'
                           : 'bg-gray-50 border-gray-200 text-gray-500 hover:bg-gray-100'}">
        ${s.enabled ? t('common.yes') : t('common.no')}
      </button>`;
  }

  columns = () => [
    { key: 'order',    label: t('scripts.order') },
    { key: 'name',     label: t('scripts.name') },
    { key: 'title',    label: t('scripts.label') },
    { key: 'filename', label: t('scripts.filename') },
    { key: 'enabled',  label: t('scripts.enabled'), renderer: (s: WorkScript) => this._interruptor(s) },
  ];
}
